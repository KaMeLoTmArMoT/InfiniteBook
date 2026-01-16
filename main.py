from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
import asyncio
from fastapi import WebSocket, WebSocketDisconnect
from ollama import AsyncClient
from pydantic import ValidationError

from utils.core_logger import log
from utils.core_models import *
from utils.prompts import *
from utils.utils import *
from utils.memory_store import MemoryStore
from utils.utils import _tail_chars, _build_write_context

app = FastAPI()
ollama_client = AsyncClient()
store = MemoryStore("infinitebook.sqlite")

app.mount("/static", StaticFiles(directory="templates"), name="static")
templates = Jinja2Templates(directory="templates")


# --- ASYNC OLLAMA HELPER ---
async def call_llm_json(
        prompt: str,
        response_model: type[BaseModel],
        temperature: float,
        max_retries: int = CFG.LLM_MAX_RETRIES,
) -> BaseModel:
    schema = response_model.model_json_schema()

    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        extra = ""
        if attempt > 0:
            extra = "\nIMPORTANT: Return ONLY valid JSON matching the schema. No prose. No markdown."

        resp = await ollama_client.chat(
            model=CFG.MODEL_NAME,
            messages=[{"role": "user", "content": prompt + extra}],
            options={"temperature": temperature},
            format=schema,
        )

        raw = resp["message"]["content"]
        log_ollama_usage(log, f"LLM_CALL_ATTEMPT_{attempt}", resp)
        log.debug(f"LLM RAW OUTPUT (attempt={attempt}):\n{raw}\n" + "=" * 60)

        # Best path: validate directly from JSON string
        try:
            return response_model.model_validate_json(raw)
        except Exception as e:
            last_error = e

        # Fallback: extract JSON then validate
        data = clean_json_response(raw)
        if data is None:
            last_error = ValueError("Failed to parse JSON from model output")
            continue

        try:
            return response_model.model_validate(data)
        except ValidationError as e:
            last_error = e
            continue

    raise RuntimeError(f"LLM JSON validation failed after retries: {last_error}")


# --- ENDPOINTS ---

@app.on_event("startup")
async def startup_event():
    await store.a_init_db()


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

    result: WriteBeatResponse = await call_llm_json(prompt, WriteBeatResponse, temperature=CFG.TEMP_BEATS)
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
    await websocket.accept()
    try:
        while True:
            gpu = get_gpu_status()
            ollama_stat = await check_ollama_status()

            data = {
                "gpu": gpu,
                "ollama": ollama_stat
            }

            await websocket.send_json(data)
            await asyncio.sleep(CFG.MONITOR_INTERVAL_SEC)  # Оновлення щосекунди
    except WebSocketDisconnect:
        print("Monitor disconnected")
    except Exception as e:
        print(f"Monitor error: {e}")


if __name__ == "__main__":
    import uvicorn

    # Now we run simple uvicorn start because we are in __main__
    # Note: "main:app" string style is needed for reload=True to work
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
