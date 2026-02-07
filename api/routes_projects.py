# api/routes_projects.py
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import FileResponse

from api.routes_imggen import mgr as IMG_MGR
from utils.imggen.character_service import (
    generate_character_image_task,
    service_generate_anchors,
    service_get_image_path,
    service_get_image_result,
    service_get_image_status,
    service_run_character_generation_pipeline,
    service_upload_style_image,
)
from utils.imggen.cover_service import (
    _generate_cover_image_task,
    _kv_job_key,
    _kv_result_key,
)
from utils.imggen.job_utils import _attach_task_logger
from utils.imggen.scene_service import (
    _kv_scene_job_key,
    _kv_scene_result_key,
    service_run_scene_generation_pipeline,
)
from utils.prompts import *
from utils.pydantic_models import *
from utils.utils import *
from utils.utils import _build_write_context

router = APIRouter(prefix="/api", tags=["projects"])


# --- COVER IMAGE ---
@router.post("/projects/{project_id}/generatecover")
async def generate_cover(request: Request, project_id: str):
    await require_project(request.app.state.store, project_id)
    task = asyncio.create_task(_generate_cover_image_task(request, project_id, IMG_MGR))
    _attach_task_logger(task, f"cover:{project_id}")
    return {"ok": True}  # TODO: random seed


@router.get("/projects/{project_id}/cover/status")
async def cover_status(request: Request, project_id: str):
    ps = await require_project(request.app.state.store, project_id)
    return await ps.a_kv_get(_kv_job_key("cover")) or {"status": "IDLE"}


@router.get("/projects/{project_id}/cover/result")
async def cover_result(request: Request, project_id: str):
    ps = await require_project(request.app.state.store, project_id)
    obj = await ps.a_kv_get(_kv_result_key("cover")) or {}
    if obj.get("saved_path"):
        obj["image_url"] = f"/api/projects/{project_id}/cover/image"
    return obj


@router.get("/projects/{project_id}/cover/image")
async def cover_image(request: Request, project_id: str):
    ps = await require_project(request.app.state.store, project_id)
    res = await ps.a_kv_get(_kv_result_key("cover")) or {}
    saved_path = res.get("saved_path")
    if not saved_path:
        raise HTTPException(status_code=404, detail="cover not generated")

    p = Path(saved_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="cover file missing")

    return FileResponse(str(p), media_type="image/png")


# --- MAIN STEPS ---


@router.post("/projects/{project_id}/characters")
async def generate_characters(
    request: Request, project_id: str, req: CharactersRequest
):
    log.info(f"Step 3: Generating characters text. Project={project_id}")

    store = request.app.state.store
    model = request.app.state.model
    ps = await require_project(store, project_id)

    project_lang_code = await store.a_get_project_language(project_id)
    project_language = lang_label(project_lang_code)

    chars_resp = await call_llm_json(
        model,
        PROMPT_CHARACTERS.format(
            title=req.title,
            genre=req.genre,
            plot_summary=req.plot_summary,
            hard_rules=HARD_RULES_GENERAL,
            hard_rules_consistency=HARD_RULES_NO_NEW_MAIN_CHARS,
            prot_min=CFG.PROTAGONISTS_MIN,
            prot_max=CFG.PROTAGONISTS_MAX,
            ant_min=CFG.ANTAGONISTS_MIN,
            side_min=CFG.SUPPORTING_MIN,
            side_max=CFG.SUPPORTING_MAX,
            language=project_language,
        ),
        CharactersResponse,
        temperature=CFG.TEMP_CHARACTERS,
    )

    payload = chars_resp.model_dump()
    await ps.a_save_characters(payload)

    db_chars = await ps.a_list_characters_grouped()

    tasks_count = await service_run_character_generation_pipeline(
        request=request,
        project_id=project_id,
        title=req.title,
        genre=req.genre,
        setting=(req.setting if hasattr(req, "setting") else ""),
        db_chars=db_chars,
        img_mgr=IMG_MGR,
    )

    log.info(f"Step 3 complete. Text saved. {tasks_count} image tasks started.")

    return db_chars


@router.post("/projects/{project_id}/refine")
async def refine_idea(request: Request, project_id: str, req: RefineRequest):
    store = request.app.state.store
    model = request.app.state.model
    log.info(
        f"Step 1: Refining idea. Genre='{req.genre}', Idea='{req.idea[:50]}...', Project={project_id}"
    )
    project_lang_code = await store.a_get_project_language(project_id)
    project_language = lang_label(project_lang_code)

    prompt = PROMPT_REFINE.format(
        genre=req.genre,
        idea=req.idea,
        hard_rules=HARD_RULES_GENERAL,
        n_variations=CFG.REFINE_VARIATIONS,
        language=project_language,
    )

    refined: RefineResponse = await call_llm_json(
        model, prompt, RefineResponse, temperature=CFG.TEMP_REFINE
    )

    original = {
        "title": "Original Concept",
        "genre": req.genre,
        "description": req.idea,
    }
    options = [original] + [v.model_dump() for v in refined.variations]
    return {"options": options}


@router.post("/projects/{project_id}/plot")
async def generate_plot(request: Request, project_id: str, req: PlotRequest):
    store = request.app.state.store
    model = request.app.state.model
    ps = await require_project(store, project_id)

    await ps.a_kv_set("selected", req.model_dump())
    job = await ps.a_kv_get(_kv_job_key("cover")) or {}
    if job.get("status") != "RUNNING":
        log.info(
            f"Step 2.1: Generating image. Project={project_id}, Title='{req.title}'"
        )
        task = asyncio.create_task(
            _generate_cover_image_task(request, project_id, IMG_MGR)
        )
        _attach_task_logger(task, f"cover:{project_id}")
    else:
        log.info(
            f"Step 2.1: Image generation already in progress. Project={project_id}, Title='{req.title}'"
        )

    project_lang_code = await store.a_get_project_language(project_id)
    project_language = lang_label(project_lang_code)
    log.info(f"Step 2.2: Generating plot. Project={project_id}, Title='{req.title}'")

    prompt = PROMPT_PLOT.format(
        title=req.title,
        genre=req.genre,
        description=req.description,
        hard_rules=HARD_RULES_GENERAL,
        chapters_min=CFG.PLOT_CHAPTERS_MIN,
        chapters_max=CFG.PLOT_CHAPTERS_MAX,
        language=project_language,
    )

    plot: PlotResponse = await call_llm_json(
        model, prompt, PlotResponse, temperature=CFG.TEMP_PLOT
    )
    payload = plot.model_dump()
    await ps.a_kv_set("plot", payload)
    return payload


@router.post("/projects/{project_id}/chapter_plan")
async def generate_chapter_plan(
    request: Request, project_id: str, req: ChapterPlanRequest
):
    store = request.app.state.store
    model = request.app.state.model
    ps = await require_project(store, project_id)
    project_lang_code = await store.a_get_project_language(project_id)
    project_language = lang_label(project_lang_code)
    log.info(
        f"Step 4: Generating chapter beats. Project={project_id}, Chapter={req.chapter} '{req.chapter_title}'"
    )

    if req.characters and isinstance(req.characters[0], dict):
        characters_present = ", ".join(
            [c.get("name", "") for c in req.characters if c.get("name")]
        )
    else:
        characters_present = ", ".join([str(x) for x in req.characters])

    if req.chapter > 1:
        prev = req.chapter - 1
        prev_key = f"ch{prev}_continuity"

        prev_capsule = await ps.a_kv_get(prev_key)
        if not prev_capsule:
            try:
                texts = await ps.a_get_chapter_beat_texts_ordered(prev)
                if texts:
                    prompt = PROMPT_CHAPTER_CONTINUITY.format(
                        chapter_prose="\n\n".join(texts),
                        language=project_language,
                    )
                    capsule = await call_llm_json(
                        model, prompt, ChapterContinuity, temperature=0.2
                    )
                    await ps.a_kv_set(prev_key, capsule.model_dump())
            except Exception:
                log.error("Failed to build previous chapter continuity")
                pass

    prev_cont = await ps.a_get_prev_chapter_continuity(req.chapter)
    prev_excerpt = await ps.a_get_prev_chapter_ending_excerpt(
        req.chapter, max_chars=4500
    )

    prompt = PROMPT_CHAPTER_BEATS.format(
        title=req.title,
        genre=req.genre,
        chapter_title=req.chapter_title,
        chapter_summary=req.chapter_summary,
        characters_present=characters_present,
        prev_chapter_continuity=prev_cont or "(none)",
        prev_chapter_ending_excerpt=prev_excerpt or "(none)",
        hard_rules=HARD_RULES_GENERAL,
        hard_rules_consistency=HARD_RULES_NO_NEW_MAIN_CHARS,
        beats_min=CFG.BEATS_MIN,
        beats_max=CFG.BEATS_MAX,
        language=project_language,
    )

    beats: ChapterPlanResponse = await call_llm_json(
        model, prompt, ChapterPlanResponse, temperature=CFG.TEMP_BEATS
    )
    payload = beats.model_dump()
    await ps.a_kv_set(f"beats_ch{req.chapter}", payload)
    return payload


@router.get("/projects/{project_id}/write_beat")
async def write_beat(
    request: Request, project_id: str, chapter: int = 1, beat_index: int = 0
):
    store = request.app.state.store
    model = request.app.state.model
    ps = await require_project(store, project_id)
    project_lang_code = await store.a_get_project_language(project_id)
    project_language = lang_label(project_lang_code)

    beats_plan = await ps.a_kv_get(f"beats_ch{chapter}")
    if not beats_plan or "beats" not in beats_plan:
        return {"error": "No beats plan found. Run Step 4 first."}

    beats = beats_plan["beats"]
    if beat_index < 0 or beat_index >= len(beats):
        return {"error": "Invalid beat_index"}

    ctx = await _build_write_context(ps, chapter, beat_index, beats)
    cur = beats[beat_index]
    prompt = PROMPT_WRITE_BEAT.format(
        prev_text=ctx["prev_text"],
        prev_beats=ctx["prev_beats"],
        prev_chapter_note=ctx["prev_chapter_note"],
        prev_chapter_capsule=ctx["prev_chapter_capsule"],
        prev_chapter_ending=ctx["prev_chapter_ending"],
        beat_number=beat_index + 1,
        beat_type=cur.get("type", ""),
        beat_description=cur.get("description", ""),
        language=project_language,
    )

    opts = beat_generation_options(
        beat_type=cur.get("type", ""), chapter=chapter, beat_index=beat_index
    )
    result = await call_llm_json(
        model, prompt, WriteBeatResponse, temperature=CFG.TEMP_BEATS, options_extra=opts
    )

    payload = result.model_dump()
    await ps.a_kv_set(
        f"ch{chapter}_beat_{beat_index}", {"beat_index": beat_index, **payload}
    )
    return payload


# --- GENERALIZATION / CONTINUITY ---


@router.post("/projects/{project_id}/chapter/continuity")
async def build_chapter_continuity(
    request: Request, project_id: str, req: BuildContinuityRequest
):
    store = request.app.state.store
    model = request.app.state.model
    ps = await require_project(store, project_id)
    project_lang_code = await store.a_get_project_language(project_id)
    project_language = lang_label(project_lang_code)

    texts = await ps.a_get_chapter_beat_texts_ordered(req.chapter)
    prose = "\n\n".join(texts).strip()

    if not prose:
        empty = ChapterContinuity(bullets=[])
        await ps.a_kv_set(f"ch{req.chapter}_continuity", empty.model_dump())
        return empty.model_dump()

    prompt = PROMPT_CHAPTER_CONTINUITY.format(
        chapter_prose=prose,
        language=project_language,
    )
    capsule = await call_llm_json(model, prompt, ChapterContinuity, temperature=0.2)

    payload = capsule.model_dump()
    await ps.a_kv_set(f"ch{req.chapter}_continuity", payload)
    return payload


# --- CHARACTER ANCHORS AND IMGAGES CREATIONS ---


@router.post("/projects/{project_id}/characters/anchors")
async def generate_character_anchors(
    request: Request, project_id: str, req: CharactersAnchorsRequest
):
    return await service_generate_anchors(
        store=request.app.state.store,
        model=request.app.state.model,
        project_id=project_id,
        req=req,
    )


@router.post("/projects/{project_id}/characters/{char_id}/generate_image")
async def generate_character_image(request: Request, project_id: str, char_id: int):
    await require_project(request.app.state.store, project_id)

    task = asyncio.create_task(
        generate_character_image_task(
            request=request, project_id=project_id, char_id=char_id, img_mgr=IMG_MGR
        )
    )
    _attach_task_logger(task, f"charimg:{project_id}:{char_id}")
    return {"ok": True}


@router.get("/projects/{project_id}/characters/{char_id}/image/status")
async def character_image_status(request: Request, project_id: str, char_id: int):
    return await service_get_image_status(request.app.state.store, project_id, char_id)


@router.get("/projects/{project_id}/characters/{char_id}/image/result")
async def character_image_result(request: Request, project_id: str, char_id: int):
    return await service_get_image_result(request.app.state.store, project_id, char_id)


@router.get("/projects/{project_id}/characters/{char_id}/image")
async def character_image_file(request: Request, project_id: str, char_id: int):
    path = await service_get_image_path(request.app.state.store, project_id, char_id)
    return FileResponse(str(path), media_type="image/png")


@router.post("/projects/{project_id}/style_image")
async def set_style_image(
    request: Request, project_id: str, file: UploadFile = File(...)
):
    img_mgr = getattr(request.app.state, "imggenprovider", None) or IMG_MGR

    return await service_upload_style_image(
        store=request.app.state.store, img_mgr=img_mgr, project_id=project_id, file=file
    )


# --- SCENE VISUALIZATIONS ---


@router.post("/projects/{project_id}/chapters/{chapter_num}/generate_scenes")
async def generate_chapter_scenes(request: Request, project_id: str, chapter_num: int):
    await require_project(request.app.state.store, project_id)

    asyncio.create_task(
        service_run_scene_generation_pipeline(
            request=request,
            project_id=project_id,
            chapter_num=chapter_num,
            img_mgr=IMG_MGR,
        )
    )

    return {"ok": True, "message": "Scene generation started"}


@router.get("/projects/{project_id}/chapters/{chapter_num}/scenes/status")
async def get_chapter_scenes_status(
    request: Request, project_id: str, chapter_num: int
):
    """Returns statuses of all generated scenes for the chapter."""
    ps = await require_project(request.app.state.store, project_id)

    state = await ps.a_load_state(chapter=chapter_num)
    beats = state.get("beats", {}).get("beats", [])

    results = {}
    for i, _ in enumerate(beats):
        job = await ps.a_kv_get(_kv_scene_job_key(chapter_num, i))
        res = await ps.a_kv_get(_kv_scene_result_key(chapter_num, i))

        status = (job or {}).get("status", "IDLE")

        saved_path = res.get("saved_path") if res else None
        file_exists = False
        if saved_path:
            file_exists = Path(saved_path).exists()

        if status == "IDLE" and res:
            status = "DONE"

        if status == "DONE" and not file_exists:
            status = "IDLE"

        if status != "IDLE" or file_exists:
            results[i] = {
                "status": status,
                "has_image": file_exists,
                "prompt": (res or {}).get("visual_prompt"),
                "image_url": (
                    f"/api/projects/{project_id}/chapters/{chapter_num}/scenes/{i}/image"
                    if file_exists
                    else None
                ),
            }

    return {"items": results}


@router.get("/projects/{project_id}/chapters/{chapter_num}/scenes/{beat_index}/image")
async def get_scene_image(
    request: Request, project_id: str, chapter_num: int, beat_index: int
):
    ps = await require_project(request.app.state.store, project_id)
    res = await ps.a_kv_get(_kv_scene_result_key(chapter_num, beat_index)) or {}
    saved_path = res.get("saved_path")

    if not saved_path:
        raise HTTPException(status_code=404, detail="Image not found")

    p = Path(saved_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Image file missing")

    return FileResponse(str(p), media_type="image/png")
