# tts_provider_piper.py
import time

import wave
from pathlib import Path
from piper import PiperVoice, SynthesisConfig

from utils.core_logger import log
from utils.tts.tts_common import split_dialog_spans, silence_bytes


class PiperTtsProvider:
    def __init__(self, narr_model: str, dialog_model: str, lead_in_ms: int = 1000):
        self.voice_narr = PiperVoice.load(narr_model)
        self.voice_dialog = PiperVoice.load(dialog_model)
        self.lead_in_ms = lead_in_ms

        self.narr_cfg = SynthesisConfig(volume=1.0, length_scale=1.10, noise_scale=0.60, noise_w_scale=0.70,
                                        normalize_audio=False)
        self.dialog_cfg = SynthesisConfig(volume=1.0, length_scale=1.08, noise_scale=0.95, noise_w_scale=1.05,
                                          normalize_audio=False)

    def write_wav_for_text(self, text: str, out_path: str, project_lang_code: str) -> str:
        spans = split_dialog_spans(text, project_lang_code)
        log.debug("Spans: %s", spans)
        if not spans:
            raise ValueError("No text")

        out_path = str(out_path)
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path + ".tmp"

        def pick_voice(kind: str):
            return self.voice_dialog if kind == "dialog" else self.voice_narr

        def pick_cfg(kind: str):
            return self.dialog_cfg if kind == "dialog" else self.narr_cfg

        first_i = None
        first_gen = None
        first_chunk = None

        for i, s in enumerate(spans):
            if s.kind != "pause" and s.text.strip():
                first_gen = pick_voice(s.kind).synthesize(s.text.strip(), syn_config=pick_cfg(s.kind))
                first_chunk = next(first_gen)
                first_i = i
                break

        if first_chunk is None or first_gen is None or first_i is None:
            raise ValueError("No non-empty spans")

        sr, sw, ch = first_chunk.sample_rate, first_chunk.sample_width, first_chunk.sample_channels

        def ensure_fmt(chunk) -> None:
            if (chunk.sample_rate, chunk.sample_width, chunk.sample_channels) != (sr, sw, ch):
                raise ValueError("Audio format mismatch")

        t0 = time.perf_counter()
        with wave.open(tmp, "wb") as wf:
            wf.setframerate(sr)
            wf.setsampwidth(sw)
            wf.setnchannels(ch)

            if self.lead_in_ms > 0:
                wf.writeframes(silence_bytes(self.lead_in_ms, sr, sw, ch))

            ensure_fmt(first_chunk)
            wf.writeframes(first_chunk.audio_int16_bytes)
            for chunk in first_gen:
                ensure_fmt(chunk)
                wf.writeframes(chunk.audio_int16_bytes)

            for s in spans[first_i + 1:]:
                if s.kind == "pause":
                    wf.writeframes(silence_bytes(450, sr, sw, ch))
                    continue
                if not s.text.strip():
                    continue

                wf.writeframes(silence_bytes(60, sr, sw, ch))
                v = pick_voice(s.kind)
                cfg = pick_cfg(s.kind)
                for chunk in v.synthesize(s.text.strip(), syn_config=cfg):
                    ensure_fmt(chunk)
                    wf.writeframes(chunk.audio_int16_bytes)

        log.info(f"PiperTtsProvider: generated in {time.perf_counter() - t0:.2f}s")
        Path(tmp).replace(out_path)
        return out_path
