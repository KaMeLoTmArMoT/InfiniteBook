# tts_common.py
import re
from dataclasses import dataclass
from num2words import num2words

try:  # 2. OPTIONAL DEPENDENCY: transliterate
    from transliterate import translit

    HAS_TRANSLIT = True
except ImportError:
    HAS_TRANSLIT = False


def get_symbol_map(lang: str) -> dict:
    """Returns the symbol map for the specified language."""
    if lang.startswith('ru'):
        return {
            '$': ' долларов ',
            '€': ' евро ',
            '£': ' фунтов ',
            '%': ' процентов ',
            '&': ' и ',
            '+': ' плюс ',
            '=': ' равно ',
            '@': ' собака ',
            '#': ' номер ',
            '№': ' номер ',
            '§': ' параграф ',
        }
    elif lang.startswith('uk'):  # Ukrainian
        return {
            '$': ' доларів ',
            '€': ' євро ',
            '£': ' фунтів ',
            '%': ' відсотків ',
            '&': ' та ',
            '+': ' плюс ',
            '=': ' дорівнює ',
            '@': ' собака ',
            '#': ' номер ',
            '№': ' номер ',
            '§': ' параграф ',
        }
    elif lang.startswith('de'):  # German
        return {
            '$': ' Dollar ',
            '€': ' Euro ',
            '£': ' Pfund ',
            '%': ' Prozent ',
            '&': ' und ',
            '+': ' plus ',
            '=': ' gleich ',
            '@': ' at ',
            '#': ' Nummer ',
            '№': ' Nummer ',
            '§': ' Paragraf ',
        }
    else:  # Default to English
        return {
            '$': ' dollars ',
            '€': ' euros ',
            '£': ' pounds ',
            '%': ' percent ',
            '&': ' and ',
            '+': ' plus ',
            '=': ' equals ',
            '@': ' at ',
            '#': ' number ',
            '№': ' number ',
            '§': ' section ',
        }


def canon_lang(code: str | None) -> str:
    c = (code or "").strip().lower()
    if c.startswith("ru"):
        return "ru"
    if c.startswith("uk"):
        return "uk"
    if c.startswith("de"):
        return "de"
    return "en"


class TextNormalizer:
    """
    Production-ready text normalizer for TTS.
    Integrates cleaning, symbol expansion, number conversion, and whitespace collapsing.
    Mandatory: num2words.
    Optional: transliterate (if installed and enabled).
    """

    def __init__(self, lang: str = "en", use_translit: bool = False):
        self._want_translit = bool(use_translit)  # remember user intent
        self.lang = canon_lang(lang)
        self.use_translit = self._want_translit and HAS_TRANSLIT and self.lang in ["ru", "uk"]
        self.symbol_map = get_symbol_map(self.lang)

    def _basic_clean(self, text: str) -> str:
        """Removes noise characters and HTML tags."""
        # Remove noise characters that disturb TTS (*, ~, ^)
        text = re.sub(r"[\*~^]", "", text)

        # Remove simple tags like <i>...</i>, <b>, <br/>, etc. (keep inner text)
        text = re.sub(r"<[^>]+>", "", text)

        return text

    def _transliterate(self, text: str) -> str:
        """Converts Latin -> Cyrillic if enabled and supported."""
        if self.use_translit:
            try:
                # Transliterate usually expects a target language code
                return translit(text, self.lang)
            except Exception:
                return text
        return text

    def _expand_numbers(self, text: str) -> str:
        """
        Converts numbers to words (e.g., '5.' -> 'five.').
        Uses 'cardinal' type by default via num2words.
        """

        def replace_num(match):
            num_str = match.group()
            try:
                return num2words(num_str, lang=self.lang)
            except Exception:
                return num_str

        # Regex looks for numbers, preserving punctuation (commas/dots)
        return re.sub(r'\b\d+(?:[.,]\d+)?\b', replace_num, text)

    def _update_params(self, project_lang_code: str):
        new_lang = canon_lang(project_lang_code)
        if new_lang != self.lang:
            self.lang = new_lang
            self.symbol_map = get_symbol_map(self.lang)
            self.use_translit = self._want_translit and HAS_TRANSLIT and self.lang in ["ru", "uk"]

    def normalize(self, text: str, project_lang_code: str) -> str:
        """
        Main entry point. Returns a single normalized string.
        Does NOT split into sentences.
        """
        if not text:
            return ""
        self._update_params(project_lang_code)

        # 1. Basic cleaning (HTML, noise)
        text = self._basic_clean(text)

        # 2. Latin to Cyrillic (Optional, mostly for RU/UK)
        text = self._transliterate(text)

        # 3. Expand Symbols (Critical step before numbers)
        for sym, word in self.symbol_map.items():
            text = text.replace(sym, word)

        # 4. Fix Duplicates (e.g., "number number" -> "number")
        text = re.sub(r'\b(\w+)\s+\1\b', r'\1', text, flags=re.I)

        # 5. Standardize Dashes & Quotes
        text = re.sub(r'[«»„“”]', '"', text)
        text = re.sub(r'^\s*[—\-–•]\s*', '', text)  # Start of line
        text = re.sub(r'\s+[—\-–•]+\s+', ', ', text)  # Mid-sentence

        # 6. Ellipsis to Comma
        text = text.replace('...', ', ').replace('..', ', ').replace('…', ', ')

        # 7. Expand Numbers
        text = self._expand_numbers(text)

        # 8. Final Polish (Whitespace & Punctuation)
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\s+([.,!?;:])', r'\1', text)  # "word ." -> "word."
        text = re.sub(r',\s*,', ',', text)  # ", ," -> ","

        return text.strip()


# TODO: replace with per-lang cache or per-request instance if concurrency becomes an issue.
_default_normalizer = TextNormalizer(lang="en", use_translit=False)


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


def split_dialog_spans(text: str, project_lang_code: str) -> list[Span]:
    """
    Splits text into narrative and dialog spans, and applies
    full text normalization using the global default language.
    """
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    spans: list[Span] = []
    current_kind = "narr"
    buf: list[str] = []

    def flush(new_kind: str):
        nonlocal current_kind
        if buf:
            content = "".join(buf)
            # If we are in narrative mode and see double newlines, split into pauses
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

        # Handle “Smart Quotes”
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

        # Handle "Standard Quotes"
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

        # Handle 'Single Quotes'
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

    # Merge adjacent spans of the same kind
    merged: list[Span] = []
    for s in spans:
        if not s.text:
            continue
        if merged and merged[-1].kind == s.kind and s.kind != "pause":
            merged[-1] = Span(s.kind, merged[-1].text + s.text)
        else:
            merged.append(s)

    # Final pass: Normalize text and filter empty spans
    final: list[Span] = []
    for s in merged:
        if s.kind == "pause":
            final.append(s)
            continue

        # INTEGRATION: Use global TextNormalizer instance
        cleaned = _default_normalizer.normalize(s.text, canon_lang(project_lang_code))
        if cleaned:
            final.append(Span(s.kind, cleaned))

    return final


def silence_bytes(ms: int, sr: int, sw: int, ch: int) -> bytes:
    frames = int(sr * ms / 1000)
    return b"\x00" * (frames * sw * ch)
