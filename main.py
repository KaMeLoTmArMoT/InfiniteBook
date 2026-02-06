# main.py
import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from api.routes_imggen import router as imggen_router
from api.routes_projects import router as project_router
from api.routes_speech import router as speech_router
from utils.core_logger import log
from utils.memory_store import MemoryStore
from utils.models import build_model_gateway
from utils.pydantic_models import (
    CFG,
    CharacterPatch,
    ClearBeatRequest,
    ClearFromBeatRequest,
)
from utils.tts.tts_manager import TtsManager
from utils.utils import (
    check_ollama_status,
    get_cpu_status_async,
    get_gpu_status,
    get_ram_status,
    require_project,
)

SUPPORTED_PROJECT_LANGS = {"en", "ru", "de"}

if os.name == "nt":
    log.info("Setting WindowsSelectorEventLoopPolicy for asyncio on Windows")
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@asynccontextmanager
async def lifespan(app: FastAPI):
    # init shared services here
    store = MemoryStore("infinitebook.sqlite")
    model = build_model_gateway()

    await store.a_init_db()
    await model.startup()

    app.state.tts = TtsManager(CFG)  # lazy init providers
    app.state.store = store
    app.state.model = model

    yield

    try:
        await app.state.tts.unload()
    except Exception as e:
        log.exception(f"TTS unload failed on shutdown {e}")

    try:
        await app.state.model.shutdown()
    except Exception as e:
        log.exception(f"MODEL shutdown failed on shutdown {e}")


app = FastAPI(lifespan=lifespan)

app.include_router(imggen_router)
app.include_router(speech_router)
app.include_router(project_router)

log.info("Run")

app.mount("/static", StaticFiles(directory="templates"), name="static")
templates = Jinja2Templates(directory="templates")


# --- ENDPOINTS ---


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/projects", response_class=HTMLResponse, include_in_schema=False)
async def projects_page(request: Request):
    return templates.TemplateResponse("projects.html", {"request": request})


@app.get("/api/projects/{project_id}/state")
async def api_state(request: Request, project_id: str, chapter: int = 1):
    ps = await require_project(request.app.state.store, project_id)
    return await ps.a_load_state(chapter=chapter)


@app.get("/reader", response_class=HTMLResponse, include_in_schema=False)
async def reader(request: Request):
    return templates.TemplateResponse("reader.html", {"request": request})


@app.delete("/api/projects/{project_id}/characters/{char_id}")
async def delete_character(request: Request, project_id: str, char_id: int):
    ps = await require_project(request.app.state.store, project_id)
    await ps.a_delete_character(char_id)
    return {"ok": True}


@app.patch("/api/projects/{project_id}/characters/{char_id}")
async def patch_character(
    request: Request, project_id: str, char_id: int, patch: CharacterPatch
):
    ps = await require_project(request.app.state.store, project_id)
    updated = await ps.a_update_character(char_id, patch.model_dump(exclude_none=True))
    return {"ok": True, "character": updated}


@app.post("/api/projects/{project_id}/reset")
async def reset_project(request: Request, project_id: str):
    await require_project(request.app.state.store, project_id)
    await request.app.state.store.a_reset_all(project_id=project_id)
    return {"ok": True}


@app.post("/api/projects/{project_id}/beat/clear")
async def api_clear_beat(request: Request, project_id: str, req: ClearBeatRequest):
    ps = await require_project(request.app.state.store, project_id)
    log.info(
        f"Step 5: Clear beat text. Project={project_id}, Chapter={req.chapter}, beat_index={req.beat_index}"
    )
    await ps.a_clear_beat_text(req.chapter, req.beat_index)
    return {"ok": True}


@app.post("/api/projects/{project_id}/beat/clear_from")
async def api_clear_from(request: Request, project_id: str, req: ClearFromBeatRequest):
    ps = await require_project(request.app.state.store, project_id)
    log.info(
        f"Step 5: Clear beat texts from. Project={project_id}, Chapter={req.chapter}, from_beat_index={req.from_beat_index}"
    )
    await ps.a_clear_beat_texts_from(req.chapter, req.from_beat_index)
    return {"ok": True}


@app.websocket("/ws/monitor")
async def websocket_endpoint(websocket: WebSocket):
    llm_providers = [CFG.LLM_PROVIDER]
    tts_providers = [CFG.TTS_PROVIDER]

    log.info(
        f"Monitor connected, LLM providers: {llm_providers}, TTS providers: {tts_providers}"
    )

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
async def api_projects_list(
    request: Request,
):
    return {"items": await request.app.state.store.a_list_projects()}


@app.post("/api/projects")
async def api_projects_create(request: Request, payload: dict):
    title = (payload.get("title") or "").strip() or "Untitled"

    language = (payload.get("language") or "en").strip().lower()
    if language not in SUPPORTED_PROJECT_LANGS:
        language = "en"

    proj = await request.app.state.store.a_create_project(title, language)
    return {"project": proj}


@app.delete("/api/projects/{project_id}")
async def api_projects_delete(request: Request, project_id: str):
    # keep it simple: no delete default, but you can remove that rule later
    await request.app.state.store.a_delete_project(project_id)
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)
