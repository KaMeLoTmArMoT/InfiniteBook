from utils.tts.tts_provider_f5 import F5TtsProvider
from utils.tts.tts_provider_piper import PiperTtsProvider
from utils.tts.tts_provider_qwen import QwenTtsProvider
from utils.tts.tts_provider_xtts import XttsTtsProvider


def canon_lang(code: str | None) -> str:
    c = (code or "").strip().lower()
    if c.startswith("ru"):
        return "ru"
    if c.startswith("uk"):
        return "uk"
    if c.startswith("de"):
        return "de"
    return "en"


def pick_piper_models(cfg, project_lang_code: str) -> tuple[str, str]:
    lang = canon_lang(project_lang_code)
    if lang == "ru":
        return cfg.PIPER_NARR_MODEL_RU, cfg.PIPER_DIALOG_MODEL_RU
    if lang == "de":
        return cfg.PIPER_NARR_MODEL_DE, cfg.PIPER_DIALOG_MODEL_DE
    return cfg.PIPER_NARR_MODEL_EN, cfg.PIPER_DIALOG_MODEL_EN


def build_piper(cfg, project_lang_code: str) -> PiperTtsProvider:
    narr_model, dialog_model = pick_piper_models(cfg, project_lang_code)
    return PiperTtsProvider(narr_model=narr_model, dialog_model=dialog_model)


def pick_xtts_voices(cfg, project_lang_code: str) -> tuple[str, str]:
    lang = canon_lang(project_lang_code)
    if lang == "ru":
        return cfg.XTTS_NARR_VOICE_RU, cfg.XTTS_DIALOG_VOICE_RU
    return cfg.XTTS_NARR_VOICE, cfg.XTTS_DIALOG_VOICE


def build_xtts(cfg, project_lang_code: str) -> XttsTtsProvider:
    lang = canon_lang(project_lang_code)
    finetune = getattr(cfg, "XTTS_FINETUNE_DIR_RU", None) if lang == "ru" else None
    narr_voice, dialog_voice = pick_xtts_voices(cfg, project_lang_code)
    return XttsTtsProvider(
        model_name=cfg.XTTS_MODEL,
        narr_voice=narr_voice,
        dialog_voice=dialog_voice,
        language=lang,
        fade_ms=cfg.XTTS_FADE_MS,
        finetune_dir=finetune,
    )


def build_qwen(cfg) -> QwenTtsProvider:
    return QwenTtsProvider(
        api_url=cfg.QWEN_TTS_URL,
        model_id=cfg.QWEN_MODEL_ID,
        dtype=getattr(cfg, "QWEN_DTYPE", "float16"),
    )


def build_f5(cfg) -> F5TtsProvider:
    return F5TtsProvider(
        ckpt_ru=cfg.F5_CKPT_RU,
        ckpt_en=cfg.F5_CKPT_EN,
        ref_audio_ru=cfg.F5_REF_AUDIO_RU,
        ref_text_ru=cfg.F5_REF_TEXT_RU,
        ref_audio_en=cfg.F5_REF_AUDIO_EN,
        ref_text_en=cfg.F5_REF_TEXT_EN,
        device=cfg.DEVICE,
        speed=0.8,
        nfe_step=64,
    )
