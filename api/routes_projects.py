# api/routes_projects.py
from __future__ import annotations

from fastapi import APIRouter, Request

from utils.core_logger import log
from utils.core_models import *
from utils.prompts import *
from utils.utils import *
from utils.utils import _build_write_context

router = APIRouter(prefix="/api", tags=["projects"])


# --- ASYNC OLLAMA HELPER ---
async def call_llm_json(
    model,
    prompt: str,
    response_model: type[BaseModel],
    temperature: float,
    max_retries: int = CFG.LLM_MAX_RETRIES,
    options_extra: dict | None = None,
) -> BaseModel:
    return await model.generate_json_validated(
        prompt,
        response_model,
        temperature=temperature,
        max_retries=max_retries,
        options=options_extra,
        tag="call_llm_json",
    )


@router.post("/projects/{project_id}/characters")
async def generate_characters(
    request: Request, project_id: str, req: CharactersRequest
):
    store = request.app.state.store
    model = request.app.state.model
    ps = await require_project(store, project_id)
    project_lang_code = await store.a_get_project_language(project_id)
    project_language = lang_label(project_lang_code)
    # (same body as before, but replace `store` -> `ps`)
    chars = await call_llm_json(
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
    payload = chars.model_dump()
    await ps.a_save_characters(payload)
    return payload


@router.post("/projects/{project_id}/refine")
async def refine_idea(request: Request, project_id: str, req: RefineRequest):
    store = request.app.state.store
    model = request.app.state.model
    log.info(
        f"Step 1: Refining idea. Genre='{req.genre}', Idea='{req.idea}', Project={project_id}"
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
    project_lang_code = await store.a_get_project_language(project_id)
    project_language = lang_label(project_lang_code)
    log.info(f"Step 2: Generating plot. Project={project_id}, Title='{req.title}'")

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
    await ps.a_kv_set("selected", req.model_dump())
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
