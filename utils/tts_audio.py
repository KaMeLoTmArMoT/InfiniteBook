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


def is_word_char(ch: str | None) -> bool:
    if ch is None:
        return False
    return bool(re.match(r"[A-Za-z0-9_]", ch))


def is_boundary(ch: str | None) -> bool:
    # boundary = start/end OR not a "word char"
    return ch is None or not is_word_char(ch)


def split_dialog_spans(text: str) -> list[Span]:
    # Normalize newlines first
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    # Collapse 3+ newlines to 2 (pause)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    spans: list[Span] = []
    current_kind = "narr"
    buf = []

    def flush(new_kind: str):
        nonlocal current_kind
        if buf:
            content = "".join(buf)
            # detect explicit pause (double newline) in narr
            if current_kind == "narr" and "\n\n" in content:
                # split by pause if present
                parts = content.split("\n\n")
                for idx, p in enumerate(parts):
                    if p:
                        spans.append(Span("narr", p))
                    if idx < len(parts) - 1:
                        spans.append(Span("pause", "\n\n"))
            else:
                spans.append(Span(current_kind, content))
        buf.clear()
        current_kind = new_kind

    i = 0
    n = len(text)

    while i < n:
        ch = text[i]
        prev = text[i - 1] if i > 0 else None

        # Check for dialogue start
        # 1. Curly quote “
        if ch == "“":
            flush("dialog")  # switch to dialog
            # scan until ”
            start = i
            i += 1
            while i < n and text[i] != "”":
                i += 1
            # include the closing quote in the dialog span
            inner = text[start + 1: i]  # drop “ and ”
            buf.append(inner)
            flush("narr")  # switch back immediately after block ends
            i += 1
            continue

        # 2. Double quote "
        if ch == '"':
            # optional: require boundary before (matches JS logic)
            if is_boundary(prev):
                flush("dialog")
                start = i
                i += 1
                while i < n:
                    if text[i] == '"' and text[i - 1] != "\\":
                        break
                    i += 1
                inner = text[start + 1: i]  # drop " and "
                buf.append(inner)
                flush("narr")
                i += 1
                continue

        # 3. Single quote ' (but not apostrophe)
        if ch == "'":
            if is_boundary(prev):
                # scan ahead to see if it's a valid quoted string
                j = i + 1
                found_close = False
                while j < n:
                    if text[j] == "'":
                        before = text[j - 1]
                        after = text[j + 1] if j + 1 < n else None

                        is_apostrophe = is_word_char(before) and is_word_char(after)
                        is_closing = (not is_apostrophe) and is_boundary(after)

                        if is_closing:
                            found_close = True
                            break
                    j += 1

                if found_close:
                    flush("dialog")
                    inner = text[i + 1: j]  # drop ' and '
                    buf.append(inner)
                    flush("narr")
                    i = j + 1
                    continue

        # otherwise, regular char
        buf.append(ch)
        i += 1

    flush("narr")  # final flush

    # Cleanup: merge adjacent same-kind spans (optional, but good for fewer chunks)
    merged = []
    for s in spans:
        if not s.text: continue
        if merged and merged[-1].kind == s.kind and s.kind != "pause":
            # merge
            merged[-1] = Span(s.kind, merged[-1].text + s.text)
        else:
            merged.append(s)

    # Cleanup 2: strip whitespace from text, remove empty
    final = []
    for s in merged:
        if s.kind == "pause":
            final.append(s)
            continue
        cleaned = re.sub(r"\s+", " ", s.text).strip()
        if cleaned:
            final.append(Span(s.kind, cleaned))

    return final


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

    # first span defines wav format, but we must write ALL chunks of it
    first_i = None
    first_span = None
    first_gen = None
    first_chunk = None

    for i, s in enumerate(spans):
        if s.kind != "pause" and s.text.strip():
            v = pick_voice(s.kind)
            cfg = pick_cfg(s.kind)

            first_gen = v.synthesize(s.text.strip(), syn_config=cfg)
            first_chunk = next(first_gen)  # only to read format; we'll write it + the rest
            first_i = i
            first_span = s
            break

    if first_chunk is None or first_gen is None or first_i is None or first_span is None:
        raise ValueError("No non-empty spans")

    sr, sw, ch = first_chunk.sample_rate, first_chunk.sample_width, first_chunk.sample_channels
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

        ensure_fmt(first_chunk)
        wf.writeframes(first_chunk.audio_int16_bytes)
        for chunk in first_gen:
            ensure_fmt(chunk)
            wf.writeframes(chunk.audio_int16_bytes)

        for s in spans[first_i + 1:]:
            if s.kind == "pause":
                wf.writeframes(_silence_bytes(450, sr, sw, ch))
                continue
            if not s.text.strip():
                continue

            wf.writeframes(_silence_bytes(60, sr, sw, ch))
            v = pick_voice(s.kind)
            cfg = pick_cfg(s.kind)
            chunk_count = 0
            for chunk in v.synthesize(s.text.strip(), syn_config=cfg):
                chunk_count += 1
                ensure_fmt(chunk)
                wf.writeframes(chunk.audio_int16_bytes)
            log.debug("Span kind=%s chunks=%d", s.kind, chunk_count)

    Path(tmp).replace(out_path)
