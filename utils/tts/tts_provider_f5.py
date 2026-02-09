# utils/tts/tts_provider_f5.py
import asyncio
import gc
import os
import re
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from f5_tts.infer.utils_infer import infer_process, load_model, load_vocoder

# F5-TTS
from f5_tts.model import DiT
from num2words import num2words

# RUAccent (Required)
from ruaccent import RUAccent

# Common Utils
from utils.core_logger import log
from utils.tts.tts_common import split_dialog_spans

# --- Configuration ---
PAD_SILENCE_MS = 100  # Тиша на краях (щоб не "з'їдало")
PAUSE_PARAGRAPH_MS = 300  # Пауза між абзацами
PAUSE_SENTENCE_MS = 100  # Пауза між реченнями
MAX_CHUNK_CHARS = 180  # Ліміт для нарізки

# Словник ручних виправлень наголосів
CUSTOM_STRESS_DICT = {
    "термокружки": "термокр+ужки",
    "термокружка": "термокр+ужка",
    "амулет": "амул+ет",
    "хакер": "х+акер",
    "интерфейс": "интерф+ейс",
}


class RussianAccentizer:
    def __init__(self, device="cpu"):
        self.accentizer = RUAccent()
        self.accentizer.load(
            omograph_model_size="turbo3.1",
            use_dictionary=True,
            custom_dict=CUSTOM_STRESS_DICT,
            device=device,
            workdir="ruaccent_data",
        )

    def process(self, text: str) -> str:
        return self.accentizer.process_all(text)


class F5TtsProvider:
    def __init__(
        self,
        ckpt_ru: str,
        ckpt_en: str,
        ref_audio_ru: str,
        ref_text_ru: str,
        ref_audio_en: str,
        ref_text_en: str,
        device: str | None = None,
        speed: float = 0.8,
        nfe_step: int = 64,
    ):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.ckpt_ru = ckpt_ru
        self.ckpt_en = ckpt_en

        self.refs = {
            "ru": {"narr": ref_audio_ru, "dialog": ref_audio_ru, "text": ref_text_ru},
            "en": {"narr": ref_audio_en, "dialog": ref_audio_en, "text": ref_text_en},
        }

        self.gen_config = {
            "nfe_step": nfe_step,
            "speed": speed,
            "fix_duration": None,
            "cross_fade_duration": 0.0,
        }

        # Shared resources
        self.vocoder = None

        # Swappable resources
        self.current_lang = None
        self.active_model = None
        self.ru_accentizer = None

        self._init_lock = asyncio.Lock()
        self._shared_loaded = False

        self.target_sr = 24000

    async def ainit(self) -> None:
        if self._shared_loaded:
            return

        async with self._init_lock:
            if self._shared_loaded:
                return

            log.info("F5-TTS Shared Init on %s...", self.device)
            await asyncio.to_thread(self._load_shared_assets)
            self._shared_loaded = True
            log.info("F5-TTS Shared Init done.")

    def _load_shared_assets(self):
        log.info("Loading Vocoder (Vocos)...")
        self.vocoder = load_vocoder(is_local=False)

    def _switch_model(self, lang: str):
        if self.current_lang == lang and self.active_model is not None:
            return

        log.info(f"F5-TTS Switching model: {self.current_lang} -> {lang}")

        # Unload old
        if self.active_model is not None:
            del self.active_model
            del self.ru_accentizer
            self.active_model = None
            self.ru_accentizer = None

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
            gc.collect()

        # Load new
        if lang == "ru":
            ckpt = self.ckpt_ru
            self.ru_accentizer = RussianAccentizer(device="cpu")
        else:
            ckpt = self.ckpt_en
            self.ru_accentizer = None

        if not os.path.exists(ckpt):
            raise FileNotFoundError(f"F5 Checkpoint for '{lang}' not found at: {ckpt}")

        log.info(f"Loading F5 {lang.upper()} model from {ckpt}...")
        model_cfg = dict(
            dim=1024, depth=22, heads=16, ff_mult=2, text_dim=512, conv_layers=4
        )

        self.active_model = load_model(
            DiT, model_cfg, ckpt, mel_spec_type="vocos", device=self.device
        )

        self.current_lang = lang
        log.info(f"F5-TTS {lang.upper()} loaded.")

    def unload(self) -> None:
        self.active_model = None
        self.ru_accentizer = None
        self.current_lang = None
        self.vocoder = None
        self._shared_loaded = False

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        gc.collect()
        log.info("F5-TTS fully unloaded.")

    def _ensure_shared_loaded(self) -> None:
        if not self._shared_loaded:
            raise RuntimeError(
                "F5TtsProvider not initialized; call await ainit() first"
            )

    def _normalize_audio_tensor(
        self, audio_tensor: np.ndarray, target_level: float = -1.0
    ) -> np.ndarray:
        max_val = np.abs(audio_tensor).max()
        if max_val > 0:
            return audio_tensor / max_val * (10 ** (target_level / 20))
        return audio_tensor

    def _generate_silence(self, duration_ms: int) -> np.ndarray:
        frames = int(self.target_sr * duration_ms / 1000)
        return np.zeros(frames, dtype=np.float32)

    def _apply_fade_out(self, audio: np.ndarray, duration_ms: int = 50) -> np.ndarray:
        """Applies a short fade-out to prevent 'hitting the wall' effect"""
        fade_len = int(self.target_sr * duration_ms / 1000)
        if fade_len > len(audio):
            fade_len = len(audio)

        if fade_len <= 0:
            return audio

        fade_curve = np.linspace(1.0, 0.0, fade_len, dtype=np.float32)
        audio[-fade_len:] *= fade_curve
        return audio

    def _is_punctuation_only(self, text: str) -> bool:
        cleaned = (
            text.strip()
            .replace(".", "")
            .replace(",", "")
            .replace("!", "")
            .replace("?", "")
            .replace(":", "")
            .replace(";", "")
            .replace("-", "")
            .replace('"', "")
            .replace("'", "")
        )
        return len(cleaned) == 0

    def _fix_trailing_punctuation(self, text: str) -> str:
        """
        Ensures the text chunk ends with a proper sentence terminator.
        Replaces 'weird' endings with periods or ellipsis.
        """
        t = text.strip()
        if not t:
            return t

        # 1. Replace "continuation" marks with "stop" marks
        if t.endswith((":")):
            return t[:-1] + "."
        if t.endswith(";"):
            return t[:-1] + "."
        if t.endswith(","):
            # return t[:-1] + "..."  # Comma at end -> trail off
            return t[:-1] + "."
        if t.endswith(("-", "–", "—")):
            return t.rstrip("-–—") + "."

        # 2. If no punctuation at all, add a period to force intonation drop
        # Check last char against common terminators
        if t[-1] not in ".!?…":
            return t + "."

        return t

    def _smart_split(self, text: str, max_chars: int) -> list[str]:
        text = text.strip()
        if not text:
            return []
        if len(text) <= max_chars:
            return [text]

        # 1. Level 1: Split by sentence endings (.!?)
        raw_sentences = re.split(r"(?<=[.!?])\s+", text)

        final_chunks = []
        current_buffer = ""

        def flush_buffer():
            nonlocal current_buffer
            if current_buffer:
                final_chunks.append(current_buffer.strip())
                current_buffer = ""

        for sentence in raw_sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            if len(current_buffer) + len(sentence) + 1 <= max_chars:
                current_buffer = (
                    (current_buffer + " " + sentence) if current_buffer else sentence
                )
            else:
                flush_buffer()
                if len(sentence) <= max_chars:
                    current_buffer = sentence
                else:
                    # Level 2: Split by commas/semicolons
                    sub_parts = re.split(r"(?<=[,;:])\s+", sentence)
                    sub_buffer = ""
                    for part in sub_parts:
                        part = part.strip()
                        if not part:
                            continue

                        if len(sub_buffer) + len(part) + 1 <= max_chars:
                            sub_buffer = (
                                (sub_buffer + " " + part) if sub_buffer else part
                            )
                        else:
                            if sub_buffer:
                                final_chunks.append(sub_buffer.strip())
                            sub_buffer = part
                    if sub_buffer:
                        final_chunks.append(sub_buffer.strip())

        flush_buffer()
        return final_chunks

    def write_wav_for_text(
        self, text: str, out_path: str, project_lang_code: str = "en"
    ) -> str:
        self._ensure_shared_loaded()

        lang = "ru" if project_lang_code == "ru" else "en"
        self._switch_model(lang)

        # 1. High-level split (Dialogue vs Narrator)
        spans = split_dialog_spans(text, lang, normalize=True)
        log.debug(f"F5-TTS Spans: {len(spans)}")

        if not spans:
            raise ValueError("No text spans found")

        out_path = str(out_path)
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)

        t0 = time.perf_counter()

        audio_segments = []
        pad_silence = self._generate_silence(PAD_SILENCE_MS)

        last_was_pause = False

        for span in spans:
            if span.kind == "pause":
                if not last_was_pause:
                    audio_segments.append(self._generate_silence(PAUSE_PARAGRAPH_MS))
                    last_was_pause = True
                continue

            clean_text = span.text.strip()

            if not clean_text or self._is_punctuation_only(clean_text):
                continue

            if audio_segments and not last_was_pause:
                audio_segments.append(self._generate_silence(PAUSE_SENTENCE_MS))

            last_was_pause = False

            ref_audio_path = self.refs[lang].get(span.kind, self.refs[lang]["narr"])
            ref_text_content = self.refs[lang]["text"]

            if not os.path.exists(ref_audio_path):
                ref_audio_path = self.refs[lang]["narr"]

            # 2. Sub-split long spans
            chunks = self._smart_split(clean_text, MAX_CHUNK_CHARS)

            for i, chunk in enumerate(chunks):
                chunk = chunk.strip()
                if not chunk:
                    continue

                # FIX: Ensure chunk ends with proper punctuation BEFORE accent
                # "Почти," -> "Почти..."
                # "высветилось:" -> "высветилось."
                chunk_fixed = self._fix_trailing_punctuation(chunk)

                if i > 0:
                    audio_segments.append(self._generate_silence(PAUSE_SENTENCE_MS))

                # Apply Accent (RU only)
                if lang == "ru" and self.ru_accentizer:
                    final_text = self.ru_accentizer.process(chunk_fixed)
                else:
                    final_text = chunk_fixed

                try:
                    raw_audio, sr, _ = infer_process(
                        ref_audio_path,
                        ref_text_content,
                        final_text,
                        self.active_model,
                        self.vocoder,
                        mel_spec_type="vocos",
                        device=self.device,
                        progress=None,
                        **self.gen_config,
                    )

                    # Fade out to avoid "wall hit"
                    raw_audio = self._apply_fade_out(raw_audio, duration_ms=5)

                    # Padding
                    audio_segments.append(pad_silence)
                    audio_segments.append(raw_audio)
                    audio_segments.append(pad_silence)

                except Exception as e:
                    log.error(f"F5 gen error for chunk '{final_text[:20]}...': {e}")
                    audio_segments.append(self._generate_silence(500))

        if not audio_segments:
            audio_segments.append(self._generate_silence(1000))

        full_audio = np.concatenate(audio_segments)
        full_audio = self._normalize_audio_tensor(full_audio)

        # Save (Raw only, DF removed)
        sf.write(out_path, full_audio, self.target_sr)

        elapsed = time.perf_counter() - t0
        log.info(f"F5-TTS generated {len(text)} chars in {elapsed:.2f}s (lang={lang})")

        return out_path
