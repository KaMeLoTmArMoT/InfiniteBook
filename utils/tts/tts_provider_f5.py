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

from utils.core_logger import log

# --- Optional Imports ---
try:
    from df.enhance import (
        enhance,
        init_df,
    )
    from df.enhance import load_audio as df_load_audio
    from df.enhance import save_audio as df_save_audio

    HAS_DF = True
except ImportError as e:
    HAS_DF = False
    log.warning("DeepFilterNet disabled: %s", e)

try:
    from ruaccent import RUAccent

    HAS_RUACCENT = True
except ImportError:
    HAS_RUACCENT = False
    log.warning("RUAccent not found.")


class TextNormalizer:
    def process(self, text: str) -> str:
        raise NotImplementedError


class EnglishTextNormalizer(TextNormalizer):
    def _replace_numbers(self, match):
        try:
            return num2words(int(match.group()), lang="en")
        except:
            return match.group()

    def process(self, text: str) -> str:
        text = text.replace("—", ", ").replace("-", ", ")
        text = re.sub(r"\d+", self._replace_numbers, text)
        return text


class RussianTextNormalizer(TextNormalizer):
    def __init__(self, device="cpu"):
        if HAS_RUACCENT:
            self.accentizer = RUAccent()
            self.accentizer.load(
                omograph_model_size="turbo3.1",
                use_dictionary=True,
                device=device,
                workdir="ruaccent_data",
            )
        else:
            self.accentizer = None

    def _replace_numbers(self, match):
        try:
            return num2words(int(match.group()), lang="ru")
        except:
            return match.group()

    def process(self, text: str) -> str:
        text = text.replace("—", ", ").replace("-", ", ")
        text = re.sub(r"\d+", self._replace_numbers, text)
        if self.accentizer:
            return self.accentizer.process_all(text)
        return text


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
        speed: float = 0.85,
        nfe_step: int = 64,
    ):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.ckpt_ru = ckpt_ru
        self.ckpt_en = ckpt_en
        self.refs = {
            "ru": {"audio": ref_audio_ru, "text": ref_text_ru},
            "en": {"audio": ref_audio_en, "text": ref_text_en},
        }
        self.gen_config = {
            "nfe_step": nfe_step,
            "speed": speed,
            "fix_duration": None,
            "cross_fade_duration": 0.05,
        }

        # Shared resources (loaded once)
        self.vocoder = None
        self.df_model = None
        self.df_state = None

        # Swappable resources (one active at a time)
        self.current_lang = None  # 'ru' or 'en'
        self.active_model = None
        self.active_normalizer = None

        self._init_lock = asyncio.Lock()
        self._shared_loaded = False

    async def ainit(self) -> None:
        """Loads shared heavy assets (Vocoder, DeepFilter). Specific models load on demand."""
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

        if HAS_DF:
            log.info("Loading DeepFilterNet...")
            self.df_model, self.df_state, _ = init_df()
        else:
            log.info("DeepFilterNet skipped.")

    def _switch_model(self, lang: str):
        """Swaps the DiT model in VRAM if the requested language differs from current."""
        if self.current_lang == lang and self.active_model is not None:
            return

        log.info(f"F5-TTS Switching model: {self.current_lang} -> {lang}")

        # 1. Unload old
        if self.active_model is not None:
            del self.active_model
            del self.active_normalizer
            self.active_model = None
            self.active_normalizer = None

            # Force VRAM cleanup
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
            gc.collect()

        # 2. Select config
        if lang == "ru":
            ckpt = self.ckpt_ru
            norm_cls = RussianTextNormalizer
        else:
            ckpt = self.ckpt_en
            norm_cls = EnglishTextNormalizer

        if not os.path.exists(ckpt):
            raise FileNotFoundError(f"F5 Checkpoint for '{lang}' not found at: {ckpt}")

        # 3. Load new
        log.info(f"Loading F5 {lang.upper()} model from {ckpt}...")
        model_cfg = dict(
            dim=1024, depth=22, heads=16, ff_mult=2, text_dim=512, conv_layers=4
        )

        self.active_model = load_model(
            DiT, model_cfg, ckpt, mel_spec_type="vocos", device=self.device
        )
        self.active_normalizer = norm_cls(device="cpu")  # Keep normalizer on CPU

        self.current_lang = lang
        log.info(f"F5-TTS {lang.upper()} loaded.")

    def unload(self) -> None:
        """Full unload of everything (Shared + Active)"""
        # Active
        self.active_model = None
        self.active_normalizer = None
        self.current_lang = None

        # Shared
        self.vocoder = None
        self.df_model = None
        self.df_state = None
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

    def write_wav_for_text(
        self, text: str, out_path: str, project_lang_code: str = "en"
    ) -> str:
        """
        Synchronous generation. Caller must wrap in asyncio.to_thread.
        """
        self._ensure_shared_loaded()

        # Determine language
        lang = "ru" if project_lang_code == "ru" else "en"

        # Ensure correct model is loaded (Swap if needed)
        self._switch_model(lang)

        # Prepare Refs
        ref_audio = self.refs[lang]["audio"]
        ref_text = self.refs[lang]["text"]

        if not os.path.exists(ref_audio):
            raise FileNotFoundError(f"Reference audio missing: {ref_audio}")

        out_path = str(out_path)
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)

        t0 = time.perf_counter()

        # 1. Text Normalization
        norm_text = self.active_normalizer.process(text)

        # 2. Inference
        raw_audio, sr, _ = infer_process(
            ref_audio,
            ref_text,
            norm_text,
            self.active_model,
            self.vocoder,
            mel_spec_type="vocos",
            device=self.device,
            **self.gen_config,
        )

        # 3. Normalize Volume
        raw_audio = self._normalize_audio_tensor(raw_audio)

        # 4. Save/Master
        if HAS_DF and self.df_model is not None:
            tmp_raw = out_path + ".raw.wav"
            sf.write(tmp_raw, raw_audio, sr)

            try:
                df_audio, _ = df_load_audio(tmp_raw, sr=self.df_state.sr())
                enhanced_audio = enhance(self.df_model, self.df_state, df_audio)
                df_save_audio(out_path, enhanced_audio, self.df_state.sr())
            finally:
                if os.path.exists(tmp_raw):
                    os.remove(tmp_raw)
        else:
            sf.write(out_path, raw_audio, sr)

        elapsed = time.perf_counter() - t0
        mode_str = "mastered" if (HAS_DF and self.df_model) else "raw"
        log.info(
            f"F5-TTS gen {len(text)} chars in {elapsed:.2f}s (lang={lang}, mode={mode_str})"
        )

        return out_path
