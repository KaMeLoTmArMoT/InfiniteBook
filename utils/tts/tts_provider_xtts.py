import asyncio
import os
import time
import wave
from pathlib import Path

import numpy as np
import torch
from TTS.api import TTS

from utils.config import CFG
from utils.core_logger import log
from utils.tts.tts_common import silence_bytes, split_dialog_spans


def float_to_int16_bytes(wav_float: np.ndarray) -> bytes:
    wav_float = np.asarray(wav_float, dtype=np.float32)
    wav_float = np.clip(wav_float, -1.0, 1.0)
    return (wav_float * 32767.0).astype(np.int16).tobytes()


def apply_fade_in_out(wav: np.ndarray, sr: int, fade_ms: int) -> np.ndarray:
    if fade_ms <= 0:
        return wav
    wav = np.asarray(wav, dtype=np.float32)
    k = int(sr * fade_ms / 1000)
    if k <= 1 or len(wav) < 2 * k:
        return wav
    fade_in = np.linspace(0.0, 1.0, k, dtype=np.float32)
    fade_out = fade_in[::-1]
    wav[:k] *= fade_in
    wav[-k:] *= fade_out
    return wav


def _finetune_ok(dir_path: str | None) -> bool:
    if not dir_path:
        return False
    p = Path(dir_path)
    return (p / "config.json").exists() and (p / "model.pth").exists()


class XttsTtsProvider:
    """
    XTTS provider with lazy model init.

    Contract:
      - await ainit() before first use (non-blocking for event loop)
      - unload() drops model refs and best-effort frees VRAM

    Extra:
      - optional finetuned checkpoint dir (model.pth + config.json):
        if provided + exists + loads -> use it, else fallback to default model_name.
    """

    def __init__(
        self,
        model_name: str,
        narr_voice: str,
        dialog_voice: str,
        language: str = "en",
        lead_in_ms: int = 1000,
        gap_ms: int = 60,
        pause_ms: int = 450,
        fade_ms: int = 20,
        device: str | None = None,
        finetune_dir: str | None = None,  # NEW (optional)
    ):
        self.model_name = model_name
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")

        self.tts: TTS | None = None

        self.narr_voice = narr_voice
        self.dialog_voice = dialog_voice
        self.language = language

        self.lead_in_ms = lead_in_ms
        self.gap_ms = gap_ms
        self.pause_ms = pause_ms
        self.fade_ms = fade_ms

        self.sr = 24000  # XTTS v2 outputs 24khz
        self.sw = 2
        self.ch = 1

        self.finetune_dir = finetune_dir
        self._loaded_variant = "default"

        self._init_lock = asyncio.Lock()

    async def ainit(self) -> None:
        if self.tts is not None:
            return

        async with self._init_lock:
            if self.tts is not None:
                return

            log.info("XTTS init start model=%s device=%s", self.model_name, self.device)

            def _load_default():
                return TTS(self.model_name).to(self.device)

            def _load_finetune():
                model_path = str(Path(self.finetune_dir).resolve())
                config_path = os.path.join(model_path, "config.json")
                # Your desired loading style:
                return TTS(
                    "tts_models/multilingual/multi-dataset/xtts_v2",
                    model_path=model_path,
                    config_path=config_path,
                ).to(self.device)

            # try finetune first (if configured + files exist), else default
            if _finetune_ok(self.finetune_dir):
                try:
                    log.info("XTTS trying finetune_dir=%s", self.finetune_dir)
                    self.tts = await asyncio.to_thread(_load_finetune)
                    self._loaded_variant = "finetune"
                except Exception as e:
                    log.warning(
                        "XTTS finetune load failed -> fallback to default: %r", e
                    )
                    self.tts = await asyncio.to_thread(_load_default)
                    self._loaded_variant = "default"
            else:
                self.tts = await asyncio.to_thread(_load_default)
                self._loaded_variant = "default"

            log.info(
                "XTTS init done variant=%s model=%s device=%s narr=%s dialog=%s lang=%s finetune_dir=%s",
                self._loaded_variant,
                self.model_name,
                self.device,
                self.narr_voice,
                self.dialog_voice,
                self.language,
                self.finetune_dir,
            )

    def unload(self) -> None:
        self.tts = None
        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def _ensure_loaded(self) -> None:
        if self.tts is None:
            raise RuntimeError(
                "XTTS provider is not initialized; call await ainit() first"
            )

    def _speaker_exists(self, name: str) -> bool:
        if not name or self.tts is None:
            return False
        # TTS wrapper: for XTTS usually there is .speakers list (names)
        speakers = getattr(self.tts, "speakers", None)
        if speakers and isinstance(speakers, (list, tuple, set)):
            return name in speakers
        # fallback: try synthesizer speaker_manager
        syn = getattr(self.tts, "synthesizer", None)
        sm = getattr(syn, "speaker_manager", None) if syn else None
        spk_dict = getattr(sm, "speakers", None)
        if isinstance(spk_dict, dict):
            return name in spk_dict
        return False

    def _pick_speaker(self, kind: str, project_lang_code: str) -> str:
        default = self.dialog_voice if kind == "dialog" else self.narr_voice

        if project_lang_code != "ru":
            return default

        if not CFG.XTTS_USE_VOICE_RU_CUSTOM:
            return default

        custom = (
            CFG.XTTS_DIALOG_VOICE_RU_CUSTOM
            if kind == "dialog"
            else CFG.XTTS_NARR_VOICE_RU_CUSTOM
        )
        if not custom:
            return default

        return custom if self._speaker_exists(custom) else default

    def write_wav_for_text(
        self, text: str, out_path: str, project_lang_code: str
    ) -> str:
        self._ensure_loaded()

        spans = split_dialog_spans(text, project_lang_code)
        log.debug("Spans: %s", spans)
        if not spans:
            raise ValueError("No text/spans")

        out_path = str(out_path)
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path + ".tmp"

        t0 = time.perf_counter()
        with wave.open(tmp, "wb") as wf:
            wf.setframerate(self.sr)
            wf.setsampwidth(self.sw)
            wf.setnchannels(self.ch)

            if self.lead_in_ms > 0:
                wf.writeframes(
                    silence_bytes(self.lead_in_ms, self.sr, self.sw, self.ch)
                )

            for s in spans:
                if s.kind == "pause":
                    wf.writeframes(
                        silence_bytes(self.pause_ms, self.sr, self.sw, self.ch)
                    )
                    continue

                if not s.text.strip():
                    continue

                if self.gap_ms > 0:
                    wf.writeframes(
                        silence_bytes(self.gap_ms, self.sr, self.sw, self.ch)
                    )

                speaker = self._pick_speaker(s.kind, project_lang_code)
                # log.info("Speaker: %s", speaker)

                # NOTE: tts.tts() is blocking CPU/GPU work; caller should run write_wav_for_text in to_thread.
                wav = self.tts.tts(text=s.text, speaker=speaker, language=self.language)
                wav = apply_fade_in_out(wav, sr=self.sr, fade_ms=self.fade_ms)
                wf.writeframes(float_to_int16_bytes(wav))

        log.info(
            "XttsTtsProvider: generated in %.2fs (variant=%s)",
            time.perf_counter() - t0,
            self._loaded_variant,
        )
        Path(tmp).replace(out_path)
        return out_path
