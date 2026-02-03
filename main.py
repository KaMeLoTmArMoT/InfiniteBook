# main.py
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from imggen_routes import router as imggen_router
from imggen_style_routes import router as imggen_style_router
from imggen_character_routes import router as imggen_character_router
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi import WebSocket, WebSocketDisconnect

from utils.core_logger import log
from utils.core_models import *
from utils.models import build_model_gateway
from utils.prompts import *
from utils.tts.audio_store import *
from utils.tts.tts_manager import TtsManager
from utils.tts.tts_provider_qwen import QwenTtsProvider
from utils.utils import *
from utils.memory_store import MemoryStore
from utils.utils import _build_write_context

import asyncio
from fastapi import HTTPException
from fastapi.responses import FileResponse

if os.name == "nt":
    log.info(f"Setting WindowsSelectorEventLoopPolicy for asyncio on Windows")
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

SUPPORTED_PROJECT_LANGS = {"en", "ru", "de"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    await store.a_init_db()
    await MODEL.startup()

    app.state.tts = TtsManager(CFG)  # lazy, no model loads here

    yield

    try:
        await app.state.tts.unload()
    except Exception as e:
        log.exception(f"TTS unload failed on shutdown {e}")

    await MODEL.shutdown()


app = FastAPI(lifespan=lifespan)
app.include_router(imggen_router)
app.include_router(imggen_style_router)
app.include_router(imggen_character_router)
MODEL = build_model_gateway()
log.info("Run")
store = MemoryStore("infinitebook.sqlite")

app.mount("/static", StaticFiles(directory="templates"), name="static")
templates = Jinja2Templates(directory="templates")


# --- ASYNC OLLAMA HELPER ---
async def call_llm_json(
        prompt: str,
        response_model: type[BaseModel],
        temperature: float,
        max_retries: int = CFG.LLM_MAX_RETRIES,
        options_extra: dict | None = None,
) -> BaseModel:
    return await MODEL.generate_json_validated(
        prompt,
        response_model,
        temperature=temperature,
        max_retries=max_retries,
        options=options_extra,
        tag="call_llm_json",
    )


# --- ENDPOINTS ---

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/projects", response_class=HTMLResponse, include_in_schema=False)
async def projects_page(request: Request):
    return templates.TemplateResponse("projects.html", {"request": request})


@app.get("/api/projects/{project_id}/state")
async def api_state(project_id: str, chapter: int = 1):
    ps = await require_project(store, project_id)
    return await ps.a_load_state(chapter=chapter)


@app.get("/reader", response_class=HTMLResponse, include_in_schema=False)
async def reader(request: Request):
    return templates.TemplateResponse("reader.html", {"request": request})


@app.post("/api/projects/{project_id}/characters")
async def generate_characters(project_id: str, req: CharactersRequest):
    ps = await require_project(store, project_id)
    project_lang_code = await store.a_get_project_language(project_id)
    project_language = lang_label(project_lang_code)
    # (same body as before, but replace `store` -> `ps`)
    chars = await call_llm_json(
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


@app.delete("/api/projects/{project_id}/characters/{char_id}")
async def delete_character(project_id: str, char_id: int):
    ps = await require_project(store, project_id)
    await ps.a_delete_character(char_id)
    return {"ok": True}


@app.patch("/api/projects/{project_id}/characters/{char_id}")
async def patch_character(project_id: str, char_id: int, patch: CharacterPatch):
    ps = await require_project(store, project_id)
    updated = await ps.a_update_character(char_id, patch.model_dump(exclude_none=True))
    return {"ok": True, "character": updated}


@app.post("/api/projects/{project_id}/reset")
async def reset_project(project_id: str):
    await require_project(store, project_id)
    await store.a_reset_all(project_id=project_id)
    return {"ok": True}


@app.post("/api/projects/{project_id}/beat/clear")
async def api_clear_beat(project_id: str, req: ClearBeatRequest):
    ps = await require_project(store, project_id)
    log.info(f"Step 5: Clear beat text. Project={project_id}, Chapter={req.chapter}, beat_index={req.beat_index}")
    await ps.a_clear_beat_text(req.chapter, req.beat_index)
    return {"ok": True}


@app.post("/api/projects/{project_id}/beat/clear_from")
async def api_clear_from(project_id: str, req: ClearFromBeatRequest):
    ps = await require_project(store, project_id)
    log.info(
        f"Step 5: Clear beat texts from. Project={project_id}, Chapter={req.chapter}, from_beat_index={req.from_beat_index}")
    await ps.a_clear_beat_texts_from(req.chapter, req.from_beat_index)
    return {"ok": True}


@app.post("/api/projects/{project_id}/refine")
async def refine_idea(project_id: str, req: RefineRequest):
    log.info(f"Step 1: Refining idea. Genre='{req.genre}', Idea='{req.idea}', Project={project_id}")
    project_lang_code = await store.a_get_project_language(project_id)
    project_language = lang_label(project_lang_code)

    prompt = PROMPT_REFINE.format(
        genre=req.genre,
        idea=req.idea,
        hard_rules=HARD_RULES_GENERAL,
        n_variations=CFG.REFINE_VARIATIONS,
        language=project_language,
    )

    refined: RefineResponse = await call_llm_json(prompt, RefineResponse, temperature=CFG.TEMP_REFINE)

    original = {"title": "Original Concept", "genre": req.genre, "description": req.idea}
    options = [original] + [v.model_dump() for v in refined.variations]
    return {"options": options}


@app.post("/api/projects/{project_id}/plot")
async def generate_plot(project_id: str, req: PlotRequest):
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

    plot: PlotResponse = await call_llm_json(prompt, PlotResponse, temperature=CFG.TEMP_PLOT)
    payload = plot.model_dump()
    await ps.a_kv_set("plot", payload)
    await ps.a_kv_set("selected", req.model_dump())
    return payload


@app.post("/api/projects/{project_id}/chapter_plan")
async def generate_chapter_plan(project_id: str, req: ChapterPlanRequest):
    ps = await require_project(store, project_id)
    project_lang_code = await store.a_get_project_language(project_id)
    project_language = lang_label(project_lang_code)
    log.info(f"Step 4: Generating chapter beats. Project={project_id}, Chapter={req.chapter} '{req.chapter_title}'")

    if req.characters and isinstance(req.characters[0], dict):
        characters_present = ", ".join([c.get("name", "") for c in req.characters if c.get("name")])
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
                    capsule = await call_llm_json(prompt, ChapterContinuity, temperature=0.2)
                    await ps.a_kv_set(prev_key, capsule.model_dump())
            except Exception:
                log.error("Failed to build previous chapter continuity")
                pass

    prev_cont = await ps.a_get_prev_chapter_continuity(req.chapter)
    prev_excerpt = await ps.a_get_prev_chapter_ending_excerpt(req.chapter, max_chars=4500)

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

    beats: ChapterPlanResponse = await call_llm_json(prompt, ChapterPlanResponse, temperature=CFG.TEMP_BEATS)
    payload = beats.model_dump()
    await ps.a_kv_set(f"beats_ch{req.chapter}", payload)
    return payload


@app.get("/api/projects/{project_id}/write_beat")
async def write_beat(project_id: str, chapter: int = 1, beat_index: int = 0):
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

    opts = beat_generation_options(beat_type=cur.get("type", ""), chapter=chapter, beat_index=beat_index)
    result = await call_llm_json(prompt, WriteBeatResponse, temperature=CFG.TEMP_BEATS,
                                 options_extra=opts)

    payload = result.model_dump()
    await ps.a_kv_set(f"ch{chapter}_beat_{beat_index}", {"beat_index": beat_index, **payload})
    return payload


@app.post("/api/projects/{project_id}/chapter/continuity")
async def build_chapter_continuity(project_id: str, req: BuildContinuityRequest):
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
    capsule = await call_llm_json(prompt, ChapterContinuity, temperature=0.2)

    payload = capsule.model_dump()
    await ps.a_kv_set(f"ch{req.chapter}_continuity", payload)
    return payload


@app.websocket("/ws/monitor")
async def websocket_endpoint(websocket: WebSocket):
    llm_providers = [CFG.LLM_PROVIDER]
    tts_providers = [CFG.TTS_PROVIDER]

    log.info(f"Monitor connected, LLM providers: {llm_providers}, TTS providers: {tts_providers}")

    await websocket.accept()
    try:
        while True:
            gpu = get_gpu_status()
            cpu = await get_cpu_status_async()
            ollama_stat = await check_ollama_status()

            data = {
                "providers": {
                    "llm": llm_providers,
                    "tts": tts_providers,
                },
                "gpu": gpu,
                "cpu": cpu,
                "ollama": ollama_stat,
                "ram": get_ram_status(),
            }

            await websocket.send_json(data)
            await asyncio.sleep(CFG.MONITOR_INTERVAL_SEC)
    except WebSocketDisconnect:
        print("Monitor disconnected")
    except Exception as e:
        print(f"Monitor error: {e}")


@app.get("/api/projects")
async def api_projects_list():
    return {"items": await store.a_list_projects()}


@app.post("/api/projects")
async def api_projects_create(payload: dict):
    title = (payload.get("title") or "").strip() or "Untitled"

    language = (payload.get("language") or "en").strip().lower()
    if language not in SUPPORTED_PROJECT_LANGS:
        language = "en"

    proj = await store.a_create_project(title, language)
    return {"project": proj}


@app.delete("/api/projects/{project_id}")
async def api_projects_delete(project_id: str):
    # keep it simple: no delete default, but you can remove that rule later
    await store.a_delete_project(project_id)
    return {"ok": True}


@app.post("/api/admin/tts/unload")
async def api_tts_unload(payload: dict, request: Request):
    key = payload.get("provider")  # optional
    ok = await request.app.state.tts.unload(key)
    return {"ok": ok, "status": request.app.state.tts.status()}


@app.get("/api/projects/{project_id}/audio/status")
async def api_audio_status(project_id: str, chapter: int = 1):
    ps = await require_project(store, project_id)
    st = await ps.a_load_state(chapter=chapter)
    beats = (st.get("beats") or {}).get("beats") or []
    n = len(beats)

    items = []
    for idx in range(n):
        for provider in TTS_PROVIDERS:
            p = wav_path(project_id, provider, chapter, idx)
            key = job_key(project_id, chapter, idx, provider)
            job = AUDIO_JOBS.get(key)

            if job == "generating":
                status = "generating"
            elif job == "error":
                status = "error"
            else:
                status = "ready" if p.exists() else "missing"

            items.append({
                "beat_index": idx,
                "provider": provider,
                "status": status,
                "exists": p.exists(),
                "url": wav_url(project_id, provider, chapter, idx) if p.exists() else "",
            })

    return {"project_id": project_id, "chapter": chapter, "items": items}


@app.get("/api/projects/{project_id}/audio/wav")
async def api_audio_wav(project_id: str, chapter: int, beat_index: int, provider: str):
    await require_project(store, project_id)
    provider = norm_provider(provider)

    p = wav_path(project_id, provider, chapter, beat_index)
    if not p.exists():
        raise HTTPException(status_code=404, detail="wav not found")

    return FileResponse(str(p), media_type="audio/wav")


@app.post("/api/projects/{project_id}/audio/generate")
async def api_audio_generate(project_id: str, payload: dict, request: Request):
    ps = await require_project(store, project_id)
    project_lang_code = await store.a_get_project_language(project_id)

    chapter = int(payload["chapter"])
    beat_index = int(payload["beat_index"])
    force = bool(payload.get("force", False))
    provider = norm_provider(payload.get("provider"))

    key = job_key(project_id, chapter, beat_index, provider)
    out_path = wav_path(project_id, provider, chapter, beat_index)

    if AUDIO_JOBS.get(key) == "generating":
        log.info("Generating in progress %s", out_path)
        return {"ok": True, "status": "generating", "provider": provider}

    if (not force) and out_path.exists():
        log.info("Skip generating %s, exists", out_path)
        return {"ok": True, "status": "ready", "provider": provider}

    st = await ps.a_load_state(chapter=chapter)
    text = (st.get("beat_texts") or {}).get(beat_index, "")
    text = (text or "").strip()
    if not text:
        log.warning("No text for %s", out_path)
        raise HTTPException(status_code=400, detail="beat text empty")

    AUDIO_JOBS[key] = "generating"

    async def _run():
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)

            tts_provider = await request.app.state.tts.ensure(provider, project_lang_code)

            if isinstance(tts_provider, QwenTtsProvider):
                await tts_provider.write_wav_for_text(text, str(out_path), project_lang_code)
            else:
                await asyncio.to_thread(tts_provider.write_wav_for_text, text, str(out_path), project_lang_code)

            AUDIO_JOBS[key] = "done"
        except Exception as e:
            log.warning("Error generating audio for %s: %s", out_path, e)
            AUDIO_JOBS[key] = "error"

    asyncio.create_task(_run())
    return {"ok": True, "status": "generating", "provider": provider}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)
