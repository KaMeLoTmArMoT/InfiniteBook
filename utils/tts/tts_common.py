# tts_common.py
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Span:
    kind: str  # "narr" | "dialog" | "pause"
    text: str


def is_word_char(ch: str | None) -> bool:
    if ch is None:
        return False
    return bool(re.match(r"[A-Za-z0-9_]", ch))


def is_boundary(ch: str | None) -> bool:
    return ch is None or not is_word_char(ch)


def split_dialog_spans(text: str) -> list[Span]:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    spans: list[Span] = []
    current_kind = "narr"
    buf: list[str] = []

    def flush(new_kind: str):
        nonlocal current_kind
        if buf:
            content = "".join(buf)
            if current_kind == "narr" and "\n\n" in content:
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

    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        prev = text[i - 1] if i > 0 else None

        if ch == "“":
            flush("dialog")
            start = i
            i += 1
            while i < n and text[i] != "”":
                i += 1
            buf.append(text[start + 1: i])
            flush("narr")
            i += 1
            continue

        if ch == '"':
            if is_boundary(prev):
                flush("dialog")
                start = i
                i += 1
                while i < n:
                    if text[i] == '"' and text[i - 1] != "\\":
                        break
                    i += 1
                buf.append(text[start + 1: i])
                flush("narr")
                i += 1
                continue

        if ch == "'":
            if is_boundary(prev):
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
                    buf.append(text[i + 1: j])
                    flush("narr")
                    i = j + 1
                    continue

        buf.append(ch)
        i += 1

    flush("narr")

    merged: list[Span] = []
    for s in spans:
        if not s.text:
            continue
        if merged and merged[-1].kind == s.kind and s.kind != "pause":
            merged[-1] = Span(s.kind, merged[-1].text + s.text)
        else:
            merged.append(s)

    final: list[Span] = []
    for s in merged:
        if s.kind == "pause":
            final.append(s)
            continue
        cleaned = re.sub(r"\s+", " ", s.text).strip()
        if cleaned:
            final.append(Span(s.kind, cleaned))
    return final


def silence_bytes(ms: int, sr: int, sw: int, ch: int) -> bytes:
    frames = int(sr * ms / 1000)
    return b"\x00" * (frames * sw * ch)
