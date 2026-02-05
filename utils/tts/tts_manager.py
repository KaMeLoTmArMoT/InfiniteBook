import asyncio
from dataclasses import dataclass

from utils.core_logger import log
from utils.tts.tts_factory import build_piper, build_qwen, build_xtts, canon_lang
from utils.tts.tts_provider_qwen import QwenTtsProvider


@dataclass
class LoadedTts:
    key: str  # "piper" | "xtts" | "qwen"
    lang: str | None  # canon lang (for piper/xtts); None for qwen
    provider: object


class TtsManager:
    def __init__(self, cfg):
        self.cfg = cfg
        self._lock = asyncio.Lock()
        self._loaded: LoadedTts | None = None

    async def _unload_current(self) -> None:
        cur = self._loaded
        if not cur:
            return

        log.info("TTS unload: key=%s lang=%s", cur.key, cur.lang)

        try:
            if hasattr(cur.provider, "unload"):
                cur.provider.unload()
        finally:
            self._loaded = None

    async def ensure(self, key: str, project_lang_code: str | None):
        key = (key or "").lower().strip()
        lang = canon_lang(project_lang_code) if project_lang_code else None

        async with self._lock:
            cur = self._loaded
            if cur and cur.key == key:
                if key in ("piper", "xtts") and cur.lang == lang:
                    return cur.provider
                if key == "qwen":
                    return cur.provider

            await self._unload_current()

            log.info("TTS load: key=%s lang=%s", key, lang)

            if key == "piper":
                p = build_piper(self.cfg, project_lang_code or "en")
                await p.ainit()
                self._loaded = LoadedTts(key="piper", lang=lang, provider=p)
                return p

            if key == "xtts":
                p = build_xtts(self.cfg, project_lang_code or "en")
                await p.ainit()
                self._loaded = LoadedTts(key="xtts", lang=lang, provider=p)
                return p

            if key == "qwen":
                p = build_qwen(self.cfg)
                await p.ainit()
                self._loaded = LoadedTts(key="qwen", lang=None, provider=p)
                return p

            raise ValueError(f"Unknown TTS provider: {key}")

    async def unload(self, key: str | None = None) -> bool:
        async with self._lock:
            if not self._loaded:
                return False
            if key and self._loaded.key != key:
                return False
            await self._unload_current()
            return True

    def status(self) -> dict:
        cur = self._loaded
        return {
            "loaded": bool(cur),
            "key": cur.key if cur else None,
            "lang": cur.lang if cur else None,
        }
