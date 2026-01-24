# tts_factory.py
import asyncio
from utils.core_logger import log
from utils.tts.tts_provider_piper import PiperTtsProvider
from utils.tts.tts_provider_xtts import XttsTtsProvider
from utils.tts.tts_provider_qwen import QwenTtsProvider


def make_tts_provider(cfg):
    provider_name = (cfg.TTS_PROVIDER or "piper").lower()

    if provider_name == "xtts":
        return XttsTtsProvider(
            model_name=cfg.XTTS_MODEL,
            narr_voice=cfg.XTTS_NARR_VOICE,
            dialog_voice=cfg.XTTS_DIALOG_VOICE,
            language=cfg.XTTS_LANGUAGE,
            fade_ms=cfg.XTTS_FADE_MS,
        )

    if provider_name == "piper":
        return PiperTtsProvider(
            narr_model=cfg.PIPER_NARR_MODEL,
            dialog_model=cfg.PIPER_DIALOG_MODEL,
        )

    if provider_name == "qwen":
        return QwenTtsProvider(
            api_url=cfg.QWEN_TTS_URL,
            model_id=cfg.QWEN_MODEL_ID,
            dtype=getattr(cfg, "QWEN_DTYPE", "float16"),
        )

    raise ValueError(f"Unknown TTS provider: {cfg.TTS_PROVIDER}")


async def make_tts_provider_async(cfg):
    provider_name = (cfg.TTS_PROVIDER or "piper").lower()
    log.info("TTS init start provider=%s", provider_name)

    try:
        p = await asyncio.to_thread(make_tts_provider, cfg)

        if provider_name == "qwen":
            await p.ainit()
            log.info("Init qwen TTS async client done")

        log.info("TTS init done provider=%s", provider_name)
        return p

    except Exception:
        log.exception("TTS init failed provider=%s", provider_name)
        raise
