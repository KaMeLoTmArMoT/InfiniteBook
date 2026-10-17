# utils/pydantic_models.py
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from utils.config import CFG

BeatType = Literal["Dialogue", "Action", "Description", "Internal Monologue"]


MAX_IDEA = 4000
MAX_TITLE = 200
MAX_GENRE = 80
MAX_DESC = 8000


# --- REQUEST MODELS (API input contracts) ---
class RefineRequest(BaseModel):
    genre: str = Field(min_length=1, max_length=MAX_GENRE)
    idea: str = Field(min_length=1, max_length=MAX_IDEA)


class PlotRequest(BaseModel):
    title: str = Field(min_length=1, max_length=MAX_TITLE)
    genre: str = Field(min_length=1, max_length=MAX_GENRE)
    description: str = Field(min_length=1, max_length=MAX_DESC)


class CharactersRequest(BaseModel):
    title: str = Field(min_length=1, max_length=MAX_TITLE)
    genre: str = Field(min_length=1, max_length=MAX_GENRE)
    plot_summary: str = Field(min_length=1, max_length=MAX_DESC)


class ChapterPlanRequest(BaseModel):
    chapter: int = Field(default=1, ge=1, le=10_000)
    title: str = Field(min_length=1, max_length=MAX_TITLE)
    genre: str = Field(min_length=1, max_length=MAX_GENRE)
    chapter_title: str = Field(min_length=1, max_length=MAX_TITLE)
    chapter_summary: str = Field(min_length=1, max_length=MAX_DESC)
    characters: list = Field(default_factory=list, max_length=200)


class BuildContinuityRequest(BaseModel):
    chapter: int = Field(ge=1, le=10_000)


# --- RESPONSE MODELS (LLM output contracts) ---


class WriteBeatResponse(BaseModel):
    text: str = Field(..., min_length=50)


class RefineOption(BaseModel):
    title: str
    genre: str
    description: str


class RefineResponse(BaseModel):
    variations: list[RefineOption] = Field(
        ..., min_length=CFG.REFINE_VARIATIONS, max_length=CFG.REFINE_VARIATIONS
    )


class PlotChapter(BaseModel):
    number: int = Field(..., ge=1)
    title: str
    summary: str


class PlotResponse(BaseModel):
    structure_analysis: str
    chapters: list[PlotChapter] = Field(
        ..., min_length=CFG.PLOT_CHAPTERS_MIN, max_length=CFG.PLOT_CHAPTERS_MAX
    )


class CharacterCard(BaseModel):
    name: str
    role: str
    bio: str


class CharactersResponse(BaseModel):
    protagonists: list[CharacterCard] = Field(
        ..., min_length=CFG.PROTAGONISTS_MIN, max_length=CFG.PROTAGONISTS_MAX
    )
    antagonists: list[CharacterCard] = Field(
        ..., min_length=CFG.ANTAGONISTS_MIN, max_length=CFG.ANTAGONISTS_MAX
    )
    supporting: list[CharacterCard] = Field(
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
    name: str | None = Field(default=None, max_length=MAX_TITLE)
    role: str | None = Field(default=None, max_length=MAX_GENRE)
    bio: str | None = Field(default=None, max_length=MAX_DESC)
    kind: str | None = Field(default=None, max_length=40)


class ChapterContinuity(BaseModel):
    bullets: list[str] = Field(default_factory=list, description="10–20 bullet continuity capsule")


class ClearBeatRequest(BaseModel):
    chapter: int = Field(default=1, ge=1, le=10_000)
    beat_index: int = Field(ge=0, le=10_000)


class ClearFromBeatRequest(BaseModel):
    chapter: int = Field(default=1, ge=1, le=10_000)
    from_beat_index: int = Field(ge=0, le=10_000)  # clears beats from this index onward


class UploadResp(BaseModel):
    comfy_name: str
    raw: dict


class StyleReq(BaseModel):
    prompt: str | None = Field(
        default="",
        max_length=MAX_DESC,
        description="If empty -> default cyberpunk noir Berlin prompt.",
    )


class SubmitFlux2Klein(BaseModel):
    prompt: str = Field(min_length=1, max_length=MAX_DESC)
    negative: str = Field(default="", max_length=MAX_DESC)
    width: int = Field(default=1024, ge=64, le=2048)
    height: int = Field(default=1024, ge=64, le=2048)
    steps: int = Field(default=20, ge=1, le=100)
    cfg: float = Field(default=5.0, ge=0.0, le=30.0)
    seed: int = Field(default=0, ge=0, le=2**31 - 1)
    filename_prefix: str = Field(default="Flux2-Klein", max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")


class SubmitRequest(BaseModel):
    pipeline: Literal[
        "flux2_klein_t2i", "flux2_klein_t2i_distilled", "flux2_klein_t2i_distilled_gguf"
    ]
    params: dict = Field(default_factory=dict)


class CharacterReq(BaseModel):
    style_anchor: str = Field(default="", max_length=MAX_DESC)
    scene_block: str = Field(default="", max_length=MAX_DESC)
    character_anchor: str = Field(default="", max_length=MAX_DESC)
    style_image: str = Field(
        default="", max_length=255, description="Filename in Comfy input/. Use /upload first."
    )
    width: int = Field(default=768, ge=64, le=2048)
    height: int = Field(default=1152, ge=64, le=2048)
    steps: int = Field(default=4, ge=1, le=100)
    cfg: float = Field(default=1.0, ge=0.0, le=30.0)
    seed: int = Field(default=0, ge=0, le=2**31 - 1)
    filename_prefix: str = Field(default="HERO-BASE", max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")


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
    title: str = Field(min_length=1, max_length=MAX_TITLE)
    genre: str = Field(min_length=1, max_length=MAX_GENRE)
    setting: str = Field(default="", max_length=MAX_DESC)
    characters: list[CharacterIn] = Field(max_length=50)


class ChapterSceneItem(BaseModel):
    beat_index: int = Field(..., description="The 0-based index of the beat")
    visual_description: str = Field(..., description="Visual prompt for Stable Diffusion")
    composition: str = Field(..., description="Camera angle (e.g. 'Wide shot')")
    primary_character_id: int | None = Field(
        None,
        description="ID of the main character in this scene, or null if no specific character focus",
    )


class ChapterScenesPlan(BaseModel):
    scenes: list[ChapterSceneItem]
