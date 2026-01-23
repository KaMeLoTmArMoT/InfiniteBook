# tts_provider_xtts.py
import wave
from pathlib import Path
import numpy as np
import torch
from TTS.api import TTS

from utils.core_logger import log
from utils.tts.tts_common import split_dialog_spans, silence_bytes


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


class XttsTtsProvider:
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
    ):
        self.tts = TTS(model_name).to(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        self.narr_voice = narr_voice
        self.dialog_voice = dialog_voice
        self.language = language

        self.lead_in_ms = lead_in_ms
        self.gap_ms = gap_ms
        self.pause_ms = pause_ms
        self.fade_ms = fade_ms

        self.sr = 24000  # XTTS v2 outputs 24khz.
        self.sw = 2
        self.ch = 1

    def _pick_speaker(self, kind: str) -> str:
        return self.dialog_voice if kind == "dialog" else self.narr_voice

    def write_wav_for_text(self, text: str, out_path: str) -> str:
        spans = split_dialog_spans(text)
        log.debug("Spans: %s", spans)
        if not spans:
            raise ValueError("No text/spans")

        out_path = str(out_path)
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path + ".tmp"

        with wave.open(tmp, "wb") as wf:
            wf.setframerate(self.sr)
            wf.setsampwidth(self.sw)
            wf.setnchannels(self.ch)

            if self.lead_in_ms > 0:
                wf.writeframes(silence_bytes(self.lead_in_ms, self.sr, self.sw, self.ch))

            for s in spans:
                if s.kind == "pause":
                    wf.writeframes(silence_bytes(self.pause_ms, self.sr, self.sw, self.ch))
                    continue

                if self.gap_ms > 0:
                    wf.writeframes(silence_bytes(self.gap_ms, self.sr, self.sw, self.ch))

                speaker = self._pick_speaker(s.kind)
                wav = self.tts.tts(text=s.text, speaker=speaker, language=self.language)
                wav = apply_fade_in_out(wav, sr=self.sr, fade_ms=self.fade_ms)
                wf.writeframes(float_to_int16_bytes(wav))

        Path(tmp).replace(out_path)
        return out_path
