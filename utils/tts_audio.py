import re
import wave
from dataclasses import dataclass
from pathlib import Path
from piper import PiperVoice, SynthesisConfig

from utils.core_logger import log

VOICE_NARR = PiperVoice.load("tts_models/en_US-ryan-high.onnx")
VOICE_DIALOG = PiperVoice.load("tts_models/en_GB-cori-high.onnx")

LEAD_IN_MS = 1000

NARR_CFG = SynthesisConfig(volume=1.0, length_scale=1.10, noise_scale=0.60, noise_w_scale=0.70, normalize_audio=False)
DIALOG_CFG = SynthesisConfig(volume=1.0, length_scale=0.95, noise_scale=0.80, noise_w_scale=0.90, normalize_audio=False)

DIALOG_OPEN = {'"', "“"}
DIALOG_CLOSE = {'"', "”"}

@dataclass(frozen=True)
class Span:
    kind: str  # "narr" | "dialog" | "pause"
    text: str

def split_dialog_spans(text: str) -> list[Span]:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    spans: list[Span] = []
    buf: list[str] = []
    in_dialog = False
    opener = None

    def flush(kind: str):
        s = "".join(buf)
        buf.clear()
        if s:
            spans.append(Span(kind, s))

    i = 0
    while i < len(text):
        if text.startswith("\n\n", i):
            flush("dialog" if in_dialog else "narr")
            spans.append(Span("pause", "\n\n"))
            i += 2
            continue

        ch = text[i]
        if (not in_dialog) and (ch in DIALOG_OPEN):
            flush("narr")
            in_dialog = True
            opener = ch
            i += 1
            continue
        if in_dialog and (ch in DIALOG_CLOSE) and (opener is not None):
            flush("dialog")
            in_dialog = False
            opener = None
            i += 1
            continue

        buf.append(ch)
        i += 1

    flush("dialog" if in_dialog else "narr")

    out: list[Span] = []
    for s in spans:
        if s.kind == "pause":
            if out and out[-1].kind != "pause":
                out.append(s)
            continue
        cleaned = re.sub(r"\s+", " ", s.text).strip()
        if cleaned:
            out.append(Span(s.kind, cleaned))
    return out

def _silence_bytes(ms: int, sr: int, sw: int, ch: int) -> bytes:
    frames = int(sr * ms / 1000)
    return b"\x00" * (frames * sw * ch)

def write_wav_for_text(text: str, out_path: str) -> None:
    spans = split_dialog_spans(text)
    log.debug(f"Spans: {spans}")

    if not spans:
        raise ValueError("No text")

    out_path = str(out_path)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path + ".tmp"

    def pick_voice(kind: str) -> PiperVoice:
        return VOICE_DIALOG if kind == "dialog" else VOICE_NARR

    def pick_cfg(kind: str) -> SynthesisConfig:
        return DIALOG_CFG if kind == "dialog" else NARR_CFG

    # first chunk defines wav format
    first = None
    first_i = None
    for i, s in enumerate(spans):
        if s.kind != "pause" and s.text.strip():
            v = pick_voice(s.kind)
            first = next(v.synthesize(s.text.strip(), syn_config=pick_cfg(s.kind)))
            first_i = i
            break
    if first is None:
        raise ValueError("No non-empty spans")

    sr, sw, ch = first.sample_rate, first.sample_width, first.sample_channels
    log.info(f"Format: sr={sr} sw={sw} ch={ch}")

    def ensure_fmt(chunk) -> None:
        if (chunk.sample_rate, chunk.sample_width, chunk.sample_channels) != (sr, sw, ch):
            raise ValueError(
                f"Audio format mismatch: got {(chunk.sample_rate, chunk.sample_width, chunk.sample_channels)} "
                f"expected {(sr, sw, ch)}"
            )

    with wave.open(tmp, "wb") as wf:
        wf.setframerate(sr)
        wf.setsampwidth(sw)
        wf.setnchannels(ch)

        if LEAD_IN_MS > 0:
            wf.writeframes(_silence_bytes(LEAD_IN_MS, sr, sw, ch))

        ensure_fmt(first)
        wf.writeframes(first.audio_int16_bytes)

        for s in spans[first_i + 1:]:
            if s.kind == "pause":
                wf.writeframes(_silence_bytes(450, sr, sw, ch))
                continue
            if not s.text.strip():
                continue

            wf.writeframes(_silence_bytes(60, sr, sw, ch))
            v = pick_voice(s.kind)
            cfg = pick_cfg(s.kind)
            for chunk in v.synthesize(s.text.strip(), syn_config=cfg):
                ensure_fmt(chunk)
                wf.writeframes(chunk.audio_int16_bytes)

    Path(tmp).replace(out_path)
