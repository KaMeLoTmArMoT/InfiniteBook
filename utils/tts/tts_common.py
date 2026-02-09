# utils/tts/tts_common.py
import re
from dataclasses import dataclass
from typing import List, Dict

from num2words import num2words

try:
    from transliterate import translit

    HAS_TRANSLIT = True
except ImportError:
    HAS_TRANSLIT = False


def get_symbol_map(lang: str) -> Dict[str, str]:
    """Returns the symbol map for the specified language."""
    if lang.startswith("ru"):
        return {
            "$": " долларов ",
            "€": " евро ",
            "£": " фунтов ",
            "%": " процентов ",
            "&": " и ",
            "+": " плюс ",
            "=": " равно ",
            "@": " собака ",
            "#": " номер ",
            "№": " номер ",
            "§": " параграф ",
        }
    elif lang.startswith("uk"):
        return {
            "$": " доларів ",
            "€": " євро ",
            "£": " фунтів ",
            "%": " відсотків ",
            "&": " та ",
            "+": " плюс ",
            "=": " дорівнює ",
            "@": " собака ",
            "#": " номер ",
            "№": " номер ",
            "§": " параграф ",
        }
    elif lang.startswith("de"):
        return {
            "$": " Dollar ",
            "€": " Euro ",
            "£": " Pfund ",
            "%": " Prozent ",
            "&": " und ",
            "+": " plus ",
            "=": " gleich ",
            "@": " at ",
            "#": " Nummer ",
            "№": " Nummer ",
            "§": " Paragraf ",
        }
    else:
        return {
            "$": " dollars ",
            "€": " euros ",
            "£": " pounds ",
            "%": " percent ",
            "&": " and ",
            "+": " plus ",
            "=": " equals ",
            "@": " at ",
            "#": " number ",
            "№": " number ",
            "§": " section ",
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


@dataclass(frozen=True)
class Span:
    kind: str  # "narr" | "dialog" | "pause"
    text: str


class TextNormalizer:
    def __init__(self, lang: str = "en", use_translit: bool = False):
        self._want_translit = bool(use_translit)
        self.lang = canon_lang(lang)
        self.use_translit = (
            self._want_translit and HAS_TRANSLIT and self.lang in ["ru", "uk"]
        )
        self.symbol_map = get_symbol_map(self.lang)

    def _basic_clean(self, text: str) -> str:
        text = re.sub(r"[\*~^]", "", text)
        text = re.sub(r"<[^>]+>", "", text)
        return text

    def _transliterate(self, text: str) -> str:
        if self.use_translit:
            try:
                return translit(text, self.lang)
            except Exception:
                return text
        return text

    def _expand_numbers(self, text: str) -> str:
        def replace_num(match):
            num_str = match.group()
            try:
                return num2words(num_str, lang=self.lang)
            except Exception:
                return num_str

        return re.sub(r"\b\d+(?:[.,]\d+)?\b", replace_num, text)

    def _update_params(self, project_lang_code: str):
        new_lang = canon_lang(project_lang_code)
        if new_lang != self.lang:
            self.lang = new_lang
            self.symbol_map = get_symbol_map(self.lang)
            self.use_translit = (
                self._want_translit and HAS_TRANSLIT and self.lang in ["ru", "uk"]
            )

    def normalize(self, text: str, project_lang_code: str) -> str:
        if not text:
            return ""
        self._update_params(project_lang_code)

        text = self._basic_clean(text)
        text = self._transliterate(text)

        for sym, word in self.symbol_map.items():
            text = text.replace(sym, word)

        text = re.sub(r"\b(\w+)\s+\1\b", r"\1", text, flags=re.I)

        text = text.replace("...", ", ").replace("..", ", ").replace("…", ", ")
        text = self._expand_numbers(text)

        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\s+([.,!?;:])", r"\1", text)
        text = re.sub(r",\s*,", ",", text)

        return text.strip()


_default_normalizer = TextNormalizer(lang="en", use_translit=False)


def split_dialog_spans(
    text: str, project_lang_code: str, normalize: bool = True
) -> List[Span]:
    """
    Splits text into narrative and dialog spans.

    Args:
        text: The source text.
        project_lang_code: Language code (e.g. 'en', 'ru').
        normalize:
            If True, applies text normalization (num2words, cleaning) - used for TTS generation.
            If False, keeps text as is (with quotes) - used for UI highlighting.
    """
    if not text:
        return []

    quote_pattern = re.compile(
        r"(«[^»]+»)|"  # Guillemets
        r"(„[^“]+“)|"  # German
        r"(“[^”]+”)|"  # Smart
        r'("[^"]+")',  # Standard
        re.DOTALL,
    )

    spans: List[Span] = []
    parts = quote_pattern.split(text)

    for idx, part in enumerate(parts):
        if not part:
            continue

        s_part = part.strip()
        is_dialog = False
        if len(s_part) >= 2:
            first, last = s_part[0], s_part[-1]
            if (
                (first == "«" and last == "»")
                or (first == "„" and last == "“")
                or (first == "“" and last == "”")
                or (first == '"' and last == '"')
            ):
                is_dialog = True

        if is_dialog:
            content = part
            if normalize:
                content = part[1:-1]
                content = _default_normalizer.normalize(content, project_lang_code)

            if content.strip():
                spans.append(Span("dialog", content))
        else:
            sub_parts = part.split("\n\n")
            for sub_idx, sub_p in enumerate(sub_parts):
                clean_p = sub_p
                if normalize:
                    clean_p = _default_normalizer.normalize(sub_p, project_lang_code)

                if clean_p.strip():
                    spans.append(Span("narr", clean_p))

                if sub_idx < len(sub_parts) - 1:
                    spans.append(Span("pause", "\n\n"))

    return spans


def silence_bytes(ms: int, sr: int, sw: int, ch: int) -> bytes:
    frames = int(sr * ms / 1000)
    return b"\x00" * (frames * sw * ch)
