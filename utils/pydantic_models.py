# utils/pydantic_models.py
from dataclasses import dataclass
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
    variations: List[RefineOption] = Field(
        ..., min_length=CFG.REFINE_VARIATIONS, max_length=CFG.REFINE_VARIATIONS
    )


class PlotChapter(BaseModel):
    number: int = Field(..., ge=1)
    title: str
    summary: str


class PlotResponse(BaseModel):
    structure_analysis: str
    chapters: List[PlotChapter] = Field(
        ..., min_length=CFG.PLOT_CHAPTERS_MIN, max_length=CFG.PLOT_CHAPTERS_MAX
    )


class CharacterCard(BaseModel):
    name: str
    role: str
    bio: str


class CharactersResponse(BaseModel):
    protagonists: List[CharacterCard] = Field(
        ..., min_length=CFG.PROTAGONISTS_MIN, max_length=CFG.PROTAGONISTS_MAX
    )
    antagonists: List[CharacterCard] = Field(
        ..., min_length=CFG.ANTAGONISTS_MIN, max_length=CFG.ANTAGONISTS_MAX
    )
    supporting: List[CharacterCard] = Field(
        ..., min_length=CFG.SUPPORTING_MIN, max_length=CFG.SUPPORTING_MAX
    )


class Beat(BaseModel):
    # type: BeatType
    type: str = Field(
        ...,
        description="Type of the beat (Dialogue, Action, Description, Internal Monologue, etc.)",
    )
    description: str


class ChapterPlanResponse(BaseModel):
    # beats: List[Beat] = Field(
    #     ..., min_length=CFG.BEATS_MIN - 1, max_length=CFG.BEATS_MAX + 3
    # )
    beats: list[Beat]


class CharacterPatch(BaseModel):
    name: str | None = None
    role: str | None = None
    bio: str | None = None
    kind: str | None = None


class ChapterContinuity(BaseModel):
    bullets: List[str] = Field(
        default_factory=list, description="10–20 bullet continuity capsule"
    )


class ClearBeatRequest(BaseModel):
    chapter: int = 1
    beat_index: int


class ClearFromBeatRequest(BaseModel):
    chapter: int = 1
    from_beat_index: int  # clears beats from this index onward


class UploadResp(BaseModel):
    comfy_name: str
    raw: dict


class StyleReq(BaseModel):
    prompt: str | None = Field(
        default="", description="If empty -> default cyberpunk noir Berlin prompt."
    )


class SubmitFlux2Klein(BaseModel):
    prompt: str = Field(min_length=1)
    negative: str = ""
    width: int = 1024
    height: int = 1024
    steps: int = 20
    cfg: float = 5.0
    seed: int = 0
    filename_prefix: str = "Flux2-Klein"


class SubmitRequest(BaseModel):
    pipeline: str = Field(min_length=1)
    params: dict = Field(default_factory=dict)


class CharacterReq(BaseModel):
    style_anchor: str = Field(default="")
    scene_block: str = Field(default="")
    character_anchor: str = Field(default="")
    style_image: str = Field(
        default="", description="Filename in Comfy input/. Use /upload first."
    )
    width: int = 768
    height: int = 1152
    steps: int = 4
    cfg: float = 1.0
    seed: int = 0
    filename_prefix: str = "HERO-BASE"


class FluxCoverPrompt(BaseModel):
    STYLE_ANCHOR: str = ""
    SCENE_BLOCK: str = ""


@dataclass(frozen=True)
class Flux2KleinT2IParams:
    prompt: str
    negative: str = ""
    width: int = 1024
    height: int = 1024
    steps: int = 20
    cfg: float = 5.0
    seed: int = 0
    filename_prefix: str = "Flux2-Klein"


@dataclass(frozen=True)
class Flux2KleinT2IDistilledParams:
    prompt: str
    width: int = 1024
    height: int = 1024
    seed: int = 0
    filename_prefix: str = "Flux2-Klein"
    steps: int = 4
    cfg: float = 1.0


@dataclass(frozen=True)
class Flux2KleinT2IDistilledGGUFParams:
    prompt: str
    width: int = 768
    height: int = 1152
    seed: int = 0
    filename_prefix: str = "Flux2-Klein"
    steps: int = 4
    cfg: float = 1.0


@dataclass(frozen=True)
class CharacterFromStyleParams:
    style_anchor: str = ""
    scene_block: str = ""
    character_anchor: str = ""
    style_image: str = ""  # filename in Comfy input/
    width: int = 768
    height: int = 1152
    steps: int = 4
    cfg: float = 1.0
    seed: int = 0
    filename_prefix: str = "HERO-BASE"


@dataclass(frozen=True)
class SceneFromStyleAndCharParams:
    style_anchor: str = ""
    scene_block: str = ""
    character_anchor: str = ""
    style_image: str = ""  # filename in Comfy input/
    char_image: str = ""  # filename in Comfy input/ (NEW)
    width: int = 1152  # Landscape default for scenes
    height: int = 768
    steps: int = 4
    cfg: float = 1.0
    seed: int = 0
    filename_prefix: str = "SCENE-DUAL-REF"


class CharacterAnchorItem(BaseModel):
    char_id: int | None = None
    name: str
    character_anchor: str


class CharacterImageAnchorsBatch(BaseModel):
    style_anchor: str
    scene_block: str
    items: list[CharacterAnchorItem] = Field(min_length=1)


class CharacterIn(BaseModel):
    id: int
    name: str
    description: str = ""


class CharactersAnchorsRequest(BaseModel):
    title: str
    genre: str
    setting: str = ""
    characters: list[CharacterIn]


class ChapterSceneItem(BaseModel):
    beat_index: int = Field(..., description="The 0-based index of the beat")
    visual_description: str = Field(
        ..., description="Visual prompt for Stable Diffusion"
    )
    composition: str = Field(..., description="Camera angle (e.g. 'Wide shot')")
    primary_character_id: int | None = Field(
        None,
        description="ID of the main character in this scene, or null if no specific character focus",
    )


class ChapterScenesPlan(BaseModel):
    scenes: list[ChapterSceneItem]
