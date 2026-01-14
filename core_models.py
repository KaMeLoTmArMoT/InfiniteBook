import json
import re
from typing import List, Literal, Optional

import ollama
import pynvml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    """
    Centralized app config.
    Can be overridden with environment variables or a .env file later.
    """
    model_config = SettingsConfigDict(env_prefix="IB_", env_file=".env", env_file_encoding="utf-8")

    # Model
    MODEL_NAME: str = "llama3.1:8b"

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
    LLM_MAX_RETRIES: int = 1

    # Monitoring
    MONITOR_INTERVAL_SEC: float = 1.0


CFG = AppConfig()

# --- HARD RULES (reused) ---
HARD_RULES_GENERAL = """\
Hard rules:
- Output must follow the requested format only.
- Do not add extra keys or commentary outside the format.
- Keep naming consistent across steps.
"""

HARD_RULES_NO_NEW_MAIN_CHARS = """\
Hard rules (consistency):
- Do NOT introduce new main characters unless explicitly requested.
- Do NOT rename characters once created.
"""


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
    title: str
    genre: str
    chapter_title: str
    chapter_summary: str
    characters: list


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


BeatType = Literal["Dialogue", "Action", "Description", "Internal Monologue"]


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


class ClearBeatRequest(BaseModel):
    chapter: int = 1
    beat_index: int


class ClearFromBeatRequest(BaseModel):
    chapter: int = 1
    from_beat_index: int  # clears beats from this index onward


# --- PROMPT TEMPLATES ---
# Keep templates as plain triple-quoted strings with .format(...) placeholders.

PROMPT_REFINE = """\
You are a professional story editor.

Task: Generate exactly {n_variations} distinct variations of the user's story premise.

Genre: {genre}
Idea: {idea}

Guidance:
- Range: Classic -> Unexpected.
- Each variation should be a compelling book blurb.
- Keep it concise, punchy, and coherent.

{hard_rules}

Return JSON only that matches the schema.
"""

PROMPT_PLOT = """\
You are a professional story architect.

Create a chapter outline for a novel.

Title: {title}
Genre: {genre}
Premise: {description}

Structure requirements:
- {chapters_min}-{chapters_max} chapters total.
- Follow: Setup -> Inciting Incident -> Rising Action -> Climax -> Resolution.
- Each chapter must have: number, title, summary.

{hard_rules}

Return JSON only that matches the schema.
"""

PROMPT_CHARACTERS = """\
You are a novelist building a cast bible.

Title: {title}
Genre: {genre}

Plot context:
{plot_summary}

Requirements:
- {prot_min}-{prot_max} protagonists with clear goal + flaw in the bio.
- {ant_min} antagonist with a clear opposing goal.
- {side_min}-{side_max} supporting characters essential to plot progression.
- No duplicate names.

{hard_rules}
{hard_rules_consistency}

Return JSON only that matches the schema.
"""

PROMPT_CHAPTER_BEATS = """\
You are a story editor writing a detailed beat sheet.

Book title: {title}
Genre: {genre}
Chapter title: {chapter_title}
Chapter summary: {chapter_summary}
Characters present: {characters_present}

Requirements:
- Produce {beats_min}-{beats_max} beats.
- Mix pacing: Dialogue, Action, Description, Internal Monologue.
- Cause -> effect progression across beats.

{hard_rules}
{hard_rules_consistency}

Return JSON only that matches the schema.
"""

PROMPT_WRITE_BEAT = """\
You are a professional novelist.

Task: Write the prose for the CURRENT beat of the chapter.

Context (previous beats descriptions):
{prev_beats}

Context (tail of previously written prose; may be empty):
\"\"\"{prev_text}\"\"\"

CURRENT beat (Beat {beat_number}, {beat_type}):
{beat_description}

Writing requirements:
- 2-6 paragraphs.
- Keep continuity with the context.
- Do not rename characters.
- Do not introduce new main characters.
- No headings, no bullet points, no markdown.

IMPORTANT OUTPUT FORMAT:
Return JSON ONLY matching the schema:
{{"text": "..."}}
"""


# --- JSON HELPERS (fallback) ---
def clean_json_response(text: str):
    """Extract JSON from a response that may contain markdown fences or extra text."""
    try:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return json.loads(text)
    except Exception:
        return None


# --- MONITORING HELPERS ---
def get_gpu_status():
    try:
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)  # Беремо першу GPU

        mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        total_mem = mem_info.total / 1024 ** 2  # MB
        used_mem = mem_info.used / 1024 ** 2  # MB

        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        gpu_load = util.gpu

        name = pynvml.nvmlDeviceGetName(handle)
        if isinstance(name, bytes): name = name.decode('utf-8')

        return {
            "name": name,
            "memory_used": int(used_mem),
            "memory_total": int(total_mem),
            "gpu_load": int(gpu_load)
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        try:
            pynvml.nvmlShutdown()
        except:
            pass


async def check_ollama_status():
    """Simple check if Ollama is responsive"""
    try:
        models = ollama.list()
        return {"status": "online", "model_count": len(models['models'])}
    except:
        return {"status": "offline", "model_count": 0}
