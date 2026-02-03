from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    """
    Centralized app config.
    Can be overridden with environment variables or a .env file later.
    """
    model_config = SettingsConfigDict(env_prefix="IB_", env_file=".env", env_file_encoding="utf-8")
    MODEL_NAME: str = "gemma3:12b"

    # Generation sizes
    REFINE_VARIATIONS: int = 5  # UI total will be +1 original
    PLOT_CHAPTERS_MIN: int = 6
    PLOT_CHAPTERS_MAX: int = 10

    PROTAGONISTS_MIN: int = 1
    PROTAGONISTS_MAX: int = 2
    ANTAGONISTS_MIN: int = 1
    ANTAGONISTS_MAX: int = 1
    SUPPORTING_MIN: int = 2
    SUPPORTING_MAX: int = 3

    BEATS_MIN: int = 10
    BEATS_MAX: int = 15

    # LLM behavior
    TEMP_REFINE: float = 0.85
    TEMP_PLOT: float = 0.70
    TEMP_CHARACTERS: float = 0.75
    TEMP_BEATS: float = 0.70
    TEMP_PROSE: float = 0.70

    LLM_MAX_RETRIES: int = 1

    # Monitoring
    MONITOR_INTERVAL_SEC: float = 1.0

    GEMINI_API: str | None = None
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL_NAME: str | None = None

    OPENROUTER_API: str | None = None
    OPENROUTER_API_KEY: str | None = None
    OPENROUTER_PRIMARY_MODEL: str | None = None
    OPENROUTER_FALLBACK_MODEL: str | None = None

    LLM_PROVIDER: str | None = None

    TTS_PROVIDER: str | None = None

    # XTTS_v2 TTS models
    XTTS_MODEL: str = "tts_models/multilingual/multi-dataset/xtts_v2"
    XTTS_NARR_VOICE: str = "Filip Traverse"
    XTTS_DIALOG_VOICE: str = "Aaron Dreschner"

    XTTS_FINETUNE_DIR_RU: str = None
    XTTS_NARR_VOICE_RU: str = "Kumar Dahl"
    XTTS_DIALOG_VOICE_RU: str = "Luis Moray"

    XTTS_USE_VOICE_RU_CUSTOM: bool = False
    XTTS_NARR_VOICE_RU_CUSTOM: str = "Alexandr Kotov"
    XTTS_DIALOG_VOICE_RU_CUSTOM: str = "Maksim Suslov"
    XTTS_FADE_MS: int = 20  # 0 => disable

    # Piper TTS models
    PIPER_NARR_MODEL_EN: str = "tts_models/piper/en_US-ryan-high.onnx"
    PIPER_DIALOG_MODEL_EN: str = "tts_models/piper/en_GB-cori-high.onnx"

    PIPER_NARR_MODEL_RU: str = "tts_models/piper/ru_RU-ruslan-medium.onnx"
    PIPER_DIALOG_MODEL_RU: str = "tts_models/piper/ru_RU-dmitri-medium.onnx"

    # Qwen TTS models
    QWEN_TTS_URL: str = "http://127.0.0.1:8001"
    QWEN_MODEL_ID: str = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
    QWEN_DTYPE: str = "float16"

    GOOGLE_GENAI_API_KEY: str | None = None
    GOOGLE_GENAI_MODEL: str | None = None

    COMFY_API_IP: str = "127.0.0.1:8188"
    COMFY_API_TIMEOUT_S: int = 300
    COMFY_TEMPLATES_DIR: str = "docs/t2i_templates"
    COMFY_OUTPUT_POLL_MS: int = 500
    COMFY_MAX_CONCURRENCY: int = 1


CFG = AppConfig()
