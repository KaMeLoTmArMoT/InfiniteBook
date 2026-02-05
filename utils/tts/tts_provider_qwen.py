# utils/tts/tts_provider_qwen.py
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

import httpx
from pydantic import BaseModel, Field

from utils.core_logger import log
from utils.tts.tts_common import split_dialog_spans

NARR_INSTRUCT = "Professional audiobook narration; steady, clear, subtle emotion."
DIALOG_INSTRUCT = (
    "Conversational, natural dialogue; slightly more expressive than narration."
)


# ----------------------------
# Request models (client-side)
# ----------------------------
class SpanIn(BaseModel):
    kind: Literal["narr", "dialog", "pause"]
    text: str = ""
    pause_ms: int = 0


class ChapterReq(BaseModel):
    book_id: Optional[str] = None
    chapter_id: Optional[str] = None

    spans: List[SpanIn]

    language: str = "English"
    speaker_map: Dict[str, str] = Field(
        default_factory=lambda: {"narr": "Aiden", "dialog": "Ryan"}
    )
    instruct_map: Dict[str, str] = Field(
        default_factory=lambda: {"narr": NARR_INSTRUCT, "dialog": DIALOG_INSTRUCT}
    )

    lead_in_ms: int = 600
    gap_ms: int = 60
    default_pause_ms: int = 450
    fade_ms: int = 18

    max_new_tokens: int = 1024
    do_sample: bool = False


# ----------------------------
# Minimal async client
# ----------------------------
@dataclass
class AsyncQwenApiClient:
    base_url: str = "http://127.0.0.1:8001"
    timeout_s: float = 300.0

    def __post_init__(self):
        # Reuse one AsyncClient; close with aclose() when done.
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout_s)

    async def aclose(self):
        await self._client.aclose()  # must be awaited

    async def state(self) -> Dict[str, Any]:
        r = await self._client.get("/state")
        r.raise_for_status()
        return r.json()

    async def load(
        self,
        model_id: str,
        dtype: str = "float16",
        attn_implementation: str = "flash_attention_2",
    ) -> Dict[str, Any]:
        r = await self._client.post(
            "/load",
            json={
                "model_id": model_id,
                "dtype": dtype,
                "attn_implementation": attn_implementation,
            },
        )
        r.raise_for_status()
        return r.json()

    async def unload(self) -> Dict[str, Any]:
        r = await self._client.post("/unload")
        r.raise_for_status()
        return r.json()

    async def generate_chapter(self, payload: ChapterReq) -> bytes:
        # We expect audio/wav bytes back.
        r = await self._client.post(
            "/generate_chapter",
            json=payload.model_dump(),
            headers={"accept": "audio/wav"},
        )
        r.raise_for_status()
        return r.content


# ----------------------------
# Provider (what your app uses)
# ----------------------------
@dataclass
class QwenTtsProvider:
    api_url: str
    model_id: str
    dtype: str = "float16"
    attn_implementation: str = "flash_attention_2"
    timeout_s: float = 300.0

    # Add these (match your other providers’ knobs)
    language: str = "English"
    lead_in_ms: int = 600
    gap_ms: int = 60
    pause_ms: int = 450
    fade_ms: int = 18

    _api: Optional["AsyncQwenApiClient"] = None
    _loaded: bool = False

    async def ainit(self) -> "QwenTtsProvider":
        self._api = AsyncQwenApiClient(base_url=self.api_url, timeout_s=self.timeout_s)
        log.info("QwenTtsProvider: load model_id=%s", self.model_id)
        await self._api.load(
            self.model_id,
            dtype=self.dtype,
            attn_implementation=self.attn_implementation,
        )
        self._loaded = True
        return self

    async def aclose(self) -> None:
        if not self._api:
            return
        try:
            await self._api.unload()
        except Exception:
            log.exception("QwenTtsProvider: unload failed (ignored)")
        await self._api.aclose()
        self._api = None
        self._loaded = False

    async def write_wav_for_text(
        self, text: str, out_path: str, project_lang_code: str
    ) -> str:
        spans = split_dialog_spans(text, project_lang_code)
        if not spans:
            raise ValueError("No text/spans")

        req_spans = []
        for s in spans:
            if s.kind == "pause":
                req_spans.append({"kind": "pause", "text": "", "pause_ms": 0})
            else:
                req_spans.append({"kind": s.kind, "text": s.text, "pause_ms": 0})

        out_path = str(out_path)
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path + ".tmp"

        t0 = time.perf_counter()
        wav_bytes = await self.generate_chapter(
            spans=req_spans,
            language=self.language,
            lead_in_ms=self.lead_in_ms,
            gap_ms=self.gap_ms,
            default_pause_ms=self.pause_ms,
            fade_ms=self.fade_ms,
        )
        log.info(f"QwenTtsProvider: generated in {time.perf_counter() - t0:.2f}s")

        Path(tmp).write_bytes(wav_bytes)
        Path(tmp).replace(out_path)  # overwrite/atomic replace semantics
        return out_path

    async def generate_chapter(
        self,
        spans: List[Dict[str, Any]] | List[SpanIn],
        *,
        language: str = "English",
        speaker_map: Optional[Dict[str, str]] = None,
        instruct_map: Optional[Dict[str, str]] = None,
        book_id: Optional[str] = None,
        chapter_id: Optional[str] = None,
        lead_in_ms: int = 600,
        gap_ms: int = 60,
        default_pause_ms: int = 450,
        fade_ms: int = 18,
        max_new_tokens: int = 1024,
        do_sample: bool = False,
        out_path: Optional[Union[str, Path]] = None,
    ) -> bytes:
        if not self._api or not self._loaded:
            raise RuntimeError(
                "QwenTtsProvider not initialized. Call await provider.ainit()."
            )

        # Accept either raw dicts or SpanIn objects
        span_models: List[SpanIn] = []
        for s in spans:
            if isinstance(s, SpanIn):
                span_models.append(s)
            else:
                span_models.append(SpanIn(**s))

        payload = ChapterReq(
            book_id=book_id,
            chapter_id=chapter_id,
            spans=span_models,
            language=language,
            speaker_map=speaker_map or {"narr": "Aiden", "dialog": "Ryan"},
            instruct_map=instruct_map
            or {"narr": NARR_INSTRUCT, "dialog": DIALOG_INSTRUCT},
            lead_in_ms=lead_in_ms,
            gap_ms=gap_ms,
            default_pause_ms=default_pause_ms,
            fade_ms=fade_ms,
            max_new_tokens=max_new_tokens,
            do_sample=do_sample,
        )

        wav_bytes = await self._api.generate_chapter(payload)

        if out_path is not None:
            out_path = Path(out_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(wav_bytes)

        return wav_bytes
