import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi import WebSocket, WebSocketDisconnect

from utils.core_logger import log
from utils.core_models import *
from utils.models import build_model_gateway
from utils.prompts import *
from utils.tts.tts_factory import make_tts_provider_async
from utils.utils import *
from utils.memory_store import MemoryStore
from utils.utils import _build_write_context

import asyncio
from pathlib import Path
from fastapi import HTTPException
from fastapi.responses import FileResponse

if os.name == "nt":
    log.info(f"Setting WindowsSelectorEventLoopPolicy for asyncio on Windows")
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@asynccontextmanager
async def lifespan(app: FastAPI):
    await store.a_init_db()
    await MODEL.startup()

    app.state.tts_provider = None
    app.state.tts_ready = asyncio.Event()
    app.state.tts_init_error = None

    async def _init_tts():
        try:
            app.state.tts_provider = await make_tts_provider_async(CFG)
            app.state.tts_ready.set()
        except Exception as e:
            app.state.tts_init_error = e
            app.state.tts_ready.set()  # unblock waiters, but with error
            log.warning(f"TTS init error: {e}")

    app.state.tts_init_task = asyncio.create_task(_init_tts())

    yield
    # shutdown
    await MODEL.shutdown()


app = FastAPI(lifespan=lifespan)
MODEL = build_model_gateway()
log.info("Run")
store = MemoryStore("infinitebook.sqlite")

app.mount("/static", StaticFiles(directory="templates"), name="static")
templates = Jinja2Templates(directory="templates")

AUDIO_JOBS = {}
AUDIO_ROOT = Path("data/wavs")


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


@app.get("/api/state")
async def api_state(chapter: int = 1):
    return await store.a_load_state(chapter=chapter)


@app.get("/reader", response_class=HTMLResponse, include_in_schema=False)
async def reader(request: Request):
    return templates.TemplateResponse("reader.html", {"request": request})


@app.delete("/api/characters/{char_id}")
async def delete_character(char_id: int):
    await store.a_delete_character(char_id)
    return {"ok": True}


@app.patch("/api/characters/{char_id}")
async def patch_character(char_id: int, patch: CharacterPatch):
    updated = await store.a_update_character(char_id, patch.model_dump(exclude_none=True))
    return {"ok": True, "character": updated}


@app.post("/api/reset")
async def reset_all():
    await store.a_reset_all()
    return {"ok": True}


@app.post("/api/beat/clear")
async def api_clear_beat(req: ClearBeatRequest):
    log.info(f"Step 5: Clear beat text. Chapter={req.chapter}, beat_index={req.beat_index}")
    await store.a_clear_beat_text(req.chapter, req.beat_index)
    return {"ok": True}


@app.post("/api/beat/clear_from")
async def api_clear_from(req: ClearFromBeatRequest):
    log.info(f"Step 5: Clear beat texts from. Chapter={req.chapter}, from_beat_index={req.from_beat_index}")
    await store.a_clear_beat_texts_from(req.chapter, req.from_beat_index)
    return {"ok": True}


@app.post("/api/refine")
async def refine_idea(req: RefineRequest):
    log.info(f"Step 1: Refining idea. Genre='{req.genre}'")

    prompt = PROMPT_REFINE.format(
        genre=req.genre,
        idea=req.idea,
        hard_rules=HARD_RULES_GENERAL,
        n_variations=CFG.REFINE_VARIATIONS,
    )

    refined: RefineResponse = await call_llm_json(prompt, RefineResponse, temperature=CFG.TEMP_REFINE)

    original = {"title": "Original Concept", "genre": req.genre, "description": req.idea}
    options = [original] + [v.model_dump() for v in refined.variations]
    return {"options": options}


@app.post("/api/plot")
async def generate_plot(req: PlotRequest):
    log.info(f"Step 2: Generating plot. Title='{req.title}'")

    prompt = PROMPT_PLOT.format(
        title=req.title,
        genre=req.genre,
        description=req.description,
        hard_rules=HARD_RULES_GENERAL,
        chapters_min=CFG.PLOT_CHAPTERS_MIN,
        chapters_max=CFG.PLOT_CHAPTERS_MAX,
    )

    plot: PlotResponse = await call_llm_json(prompt, PlotResponse, temperature=CFG.TEMP_PLOT)
    payload = plot.model_dump()
    await store.a_kv_set("plot", payload)
    await store.a_kv_set("selected", req.model_dump())
    return payload


@app.post("/api/characters")
async def generate_characters(req: CharactersRequest):
    log.info(f"Step 3: Generating characters. Title='{req.title}'")

    prompt = PROMPT_CHARACTERS.format(
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
    )

    chars: CharactersResponse = await call_llm_json(prompt, CharactersResponse, temperature=CFG.TEMP_CHARACTERS)
    payload = chars.model_dump()
    await store.a_save_characters(payload)
    return payload


@app.post("/api/chapter_plan")
async def generate_chapter_plan(req: ChapterPlanRequest):
    log.info(f"Step 4: Generating chapter beats. Chapter={req.chapter} '{req.chapter_title}'")

    if req.characters and isinstance(req.characters[0], dict):
        characters_present = ", ".join([c.get("name", "") for c in req.characters if c.get("name")])
    else:
        characters_present = ", ".join([str(x) for x in req.characters])

    if req.chapter > 1:
        prev = req.chapter - 1
        if not store.kv_get(f"ch{prev}_continuity"):
            # best-effort build, ignore failures
            try:
                texts = await store.a_get_chapter_beat_texts_ordered(prev)
                if texts:
                    prompt = PROMPT_CHAPTER_CONTINUITY.format(chapter_prose="\n\n".join(texts))
                    capsule = await call_llm_json(prompt, ChapterContinuity, temperature=0.2)
                    await store.a_kv_set(f"ch{prev}_continuity", capsule.model_dump())
            except Exception:
                log.error("Failed to build previous chapter continuity")
                pass

    prev_cont = await store.a_get_prev_chapter_continuity(req.chapter)
    prev_excerpt = await store.a_get_prev_chapter_ending_excerpt(req.chapter, max_chars=4500)

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
    )

    beats: ChapterPlanResponse = await call_llm_json(prompt, ChapterPlanResponse, temperature=CFG.TEMP_BEATS)

    payload = beats.model_dump()
    await store.a_kv_set(f"beats_ch{req.chapter}", payload)
    return payload


@app.get("/api/write_beat")
async def write_beat(chapter: int = 1, beat_index: int = 0):
    log.info(f"Step 5: Writing beat text. Chapter={chapter}, beat_index={beat_index}")

    beats_plan = await store.a_kv_get(f"beats_ch{chapter}")
    if not beats_plan or "beats" not in beats_plan:
        return {"error": "No beats plan found. Run Step 4 first."}

    beats = beats_plan["beats"]
    if beat_index < 0 or beat_index >= len(beats):
        return {"error": "Invalid beat_index"}

    ctx = await _build_write_context(store, chapter, beat_index, beats)

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
    )

    log.debug(f"\n{'=' * 20} PROMPT WRITE BEAT (Chapter={chapter}, Beat={beat_index}) {'=' * 20}\n{prompt}\n{'=' * 60}")

    opts = beat_generation_options(
        beat_type=cur.get("type", ""),
        chapter=chapter,
        beat_index=beat_index,
    )

    result: WriteBeatResponse = await call_llm_json(
        prompt, WriteBeatResponse, temperature=CFG.TEMP_BEATS, options_extra=opts,
    )
    payload = result.model_dump()

    await store.a_kv_set(f"ch{chapter}_beat_{beat_index}", {"beat_index": beat_index, **payload})
    return payload


@app.post("/api/chapter/continuity")
async def build_chapter_continuity(req: BuildContinuityRequest):
    texts = await store.a_get_chapter_beat_texts_ordered(req.chapter)
    prose = "\n\n".join(texts).strip()

    if not prose:
        empty = ChapterContinuity(bullets=[])
        await store.a_kv_set(f"ch{req.chapter}_continuity", empty.model_dump())
        return empty.model_dump()

    prompt = PROMPT_CHAPTER_CONTINUITY.format(chapter_prose=prose)

    capsule: ChapterContinuity = await call_llm_json(prompt, ChapterContinuity, temperature=0.2)

    payload = capsule.model_dump()
    await store.a_kv_set(f"ch{req.chapter}_continuity", payload)
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


def _wav_path(chapter: int, beat_index: int) -> Path:
    return AUDIO_ROOT / f"ch{chapter}" / f"beat{beat_index}.wav"


@app.get("/api/audio/status")
async def api_audio_status(chapter: int = 1):
    st = await store.a_load_state(chapter=chapter)
    beats = (st.get("beats") or {}).get("beats") or []
    n = len(beats)

    items = []
    for idx in range(n):
        p = _wav_path(chapter, idx)
        job = AUDIO_JOBS.get((chapter, idx))

        if job == "generating":
            status = "generating"
        elif job == "error":
            status = "error"
        else:
            status = "ready" if p.exists() else "missing"

        items.append({
            "beat_index": idx,
            "status": status,
            "exists": p.exists(),
            "url": f"/api/audio/wav?chapter={chapter}&beat_index={idx}" if p.exists() else "",
        })

    return {"chapter": chapter, "items": items}


@app.get("/api/audio/wav")
async def api_audio_wav(chapter: int, beat_index: int):
    p = _wav_path(chapter, beat_index)
    if not p.exists():
        raise HTTPException(status_code=404, detail="wav not found")
    return FileResponse(str(p), media_type="audio/wav")  # [web:1355]


@app.post("/api/audio/generate")
async def api_audio_generate(payload: dict, request: Request):
    tts_provider = request.app.state.tts_provider
    chapter = int(payload["chapter"])
    beat_index = int(payload["beat_index"])
    force = bool(payload.get("force", False))

    key = (chapter, beat_index)
    out_path = _wav_path(chapter, beat_index)

    if AUDIO_JOBS.get(key) == "generating":
        return {"ok": True, "status": "generating"}

    if (not force) and out_path.exists():
        return {"ok": True, "status": "ready"}

    st = await store.a_load_state(chapter=chapter)
    text = (st.get("beat_texts") or {}).get(beat_index, "")
    text = (text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="beat text empty")

    AUDIO_JOBS[key] = "generating"

    async def _run():
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(tts_provider.write_wav_for_text, text, str(out_path))  # [web:1276]
            AUDIO_JOBS[key] = "done"
        except Exception:
            AUDIO_JOBS[key] = "error"

    asyncio.create_task(_run())
    return {"ok": True, "status": "generating"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)
