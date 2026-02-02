from typing import List, Literal

from pydantic import BaseModel, Field

from utils.config import CFG

BeatType = Literal["Dialogue", "Action", "Description", "Internal Monologue"]


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
    beats: List[Beat] = Field(..., min_length=CFG.BEATS_MIN - 1, max_length=CFG.BEATS_MAX + 3)


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
