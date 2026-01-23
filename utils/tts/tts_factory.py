# tts_factory.py
import asyncio

from utils.core_logger import log
from utils.tts.tts_provider_piper import PiperTtsProvider
from utils.tts.tts_provider_xtts import XttsTtsProvider


def make_tts_provider(cfg):
    provider = (cfg.TTS_PROVIDER or "piper").lower()
    if provider == "xtts":
        return XttsTtsProvider(
            model_name=cfg.XTTS_MODEL,
            narr_voice=cfg.XTTS_NARR_VOICE,
            dialog_voice=cfg.XTTS_DIALOG_VOICE,
            language=cfg.XTTS_LANGUAGE,
            fade_ms=cfg.XTTS_FADE_MS,
        )
    if provider == "piper":
        return PiperTtsProvider(
            narr_model=cfg.PIPER_NARR_MODEL,
            dialog_model=cfg.PIPER_DIALOG_MODEL,
        )
    raise ValueError(f"Unknown TTS provider: {cfg.TTS_PROVIDER}")


async def make_tts_provider_async(cfg):
    log.info("TTS init start provider=%s", cfg.TTS_PROVIDER)
    try:
        provider = await asyncio.to_thread(make_tts_provider, cfg)  # don't block event loop
        log.info("TTS init done provider=%s", cfg.TTS_PROVIDER)
        return provider
    except Exception:
        log.exception("TTS init failed provider=%s", cfg.TTS_PROVIDER)
        raise
