# api/routes_speech.py
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from utils.core_logger import log
from utils.tts.audio_store import *
from utils.tts.tts_provider_qwen import QwenTtsProvider
from utils.utils import *

router = APIRouter(prefix="/api", tags=["tts"])


@router.post("/admin/tts/unload")
async def api_tts_unload(payload: dict, request: Request):
    key = payload.get("provider")  # optional
    ok = await request.app.state.tts.unload(key)
    return {"ok": ok, "status": request.app.state.tts.status()}


@router.get("/projects/{project_id}/audio/status")
async def api_audio_status(request: Request, project_id: str, chapter: int = 1):
    store = request.app.state.store
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

            items.append(
                {
                    "beat_index": idx,
                    "provider": provider,
                    "status": status,
                    "exists": p.exists(),
                    "url": (
                        wav_url(project_id, provider, chapter, idx)
                        if p.exists()
                        else ""
                    ),
                }
            )

    return {"project_id": project_id, "chapter": chapter, "items": items}


@router.get("/projects/{project_id}/audio/wav")
async def api_audio_wav(
    request: Request, project_id: str, chapter: int, beat_index: int, provider: str
):
    store = request.app.state.store
    await require_project(store, project_id)
    provider = norm_provider(provider)

    p = wav_path(project_id, provider, chapter, beat_index)
    if not p.exists():
        raise HTTPException(status_code=404, detail="wav not found")

    return FileResponse(str(p), media_type="audio/wav")


@router.post("/projects/{project_id}/audio/generate")
async def api_audio_generate(project_id: str, payload: dict, request: Request):
    store = request.app.state.store
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

            tts_provider = await request.app.state.tts.ensure(
                provider, project_lang_code
            )

            if isinstance(tts_provider, QwenTtsProvider):
                await tts_provider.write_wav_for_text(
                    text, str(out_path), project_lang_code
                )
            else:
                await asyncio.to_thread(
                    tts_provider.write_wav_for_text,
                    text,
                    str(out_path),
                    project_lang_code,
                )

            AUDIO_JOBS[key] = "done"
        except Exception as e:
            log.warning("Error generating audio for %s: %s", out_path, e)
            AUDIO_JOBS[key] = "error"

    asyncio.create_task(_run())
    return {"ok": True, "status": "generating", "provider": provider}
