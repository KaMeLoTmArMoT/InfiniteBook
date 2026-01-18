from typing import List, Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BeatType = Literal["Dialogue", "Action", "Description", "Internal Monologue"]


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


CFG = AppConfig()


# --- REQUEST MODELS (API input contracts) ---
class RefineRequest(BaseModel):
    genre: str
    idea: str


class PlotRequest(BaseModel):
    title: str
    genre: str
    description: str


class CharactersRequest(BaseModel):
    title: str
    genre: str
    plot_summary: str


class ChapterPlanRequest(BaseModel):
    chapter: int = 1
    title: str
    genre: str
    chapter_title: str
    chapter_summary: str
    characters: list


class BuildContinuityRequest(BaseModel):
    chapter: int


# --- RESPONSE MODELS (LLM output contracts) ---

class WriteBeatResponse(BaseModel):
    text: str = Field(..., min_length=50)


class RefineOption(BaseModel):
    title: str
    genre: str
    description: str


class RefineResponse(BaseModel):
    variations: List[RefineOption] = Field(..., min_length=CFG.REFINE_VARIATIONS, max_length=CFG.REFINE_VARIATIONS)


class PlotChapter(BaseModel):
    number: int = Field(..., ge=1)
    title: str
    summary: str


class PlotResponse(BaseModel):
    structure_analysis: str
    chapters: List[PlotChapter] = Field(..., min_length=CFG.PLOT_CHAPTERS_MIN, max_length=CFG.PLOT_CHAPTERS_MAX)


class CharacterCard(BaseModel):
    name: str
    role: str
    bio: str


class CharactersResponse(BaseModel):
    protagonists: List[CharacterCard] = Field(..., min_length=CFG.PROTAGONISTS_MIN, max_length=CFG.PROTAGONISTS_MAX)
    antagonists: List[CharacterCard] = Field(..., min_length=CFG.ANTAGONISTS_MIN, max_length=CFG.ANTAGONISTS_MAX)
    supporting: List[CharacterCard] = Field(..., min_length=CFG.SUPPORTING_MIN, max_length=CFG.SUPPORTING_MAX)


class Beat(BaseModel):
    type: BeatType
    description: str


class ChapterPlanResponse(BaseModel):
    beats: List[Beat] = Field(..., min_length=CFG.BEATS_MIN, max_length=CFG.BEATS_MAX)


class CharacterPatch(BaseModel):
    name: str | None = None
    role: str | None = None
    bio: str | None = None
    kind: str | None = None


class ChapterContinuity(BaseModel):
    bullets: List[str] = Field(default_factory=list, description="10–20 bullet continuity capsule")


class ClearBeatRequest(BaseModel):
    chapter: int = 1
    beat_index: int


class ClearFromBeatRequest(BaseModel):
    chapter: int = 1
    from_beat_index: int  # clears beats from this index onward
