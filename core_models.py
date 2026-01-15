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
    # MODEL_NAME: str = "llama3.1:8b"
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


CFG = AppConfig()

# --- HARD RULES (reused) ---
HARD_RULES_GENERAL = """\
Hard rules:
- Output must follow the requested format only.
- Do not add extra keys or commentary outside the format.
- Keep naming consistent across steps.
- Show, Don't Tell: Focus on physical actions and sensory details, not abstract feelings.
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


class ChapterContinuity(BaseModel):
    bullets: List[str] = Field(default_factory=list, description="10–20 bullet continuity capsule")


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
- Highlight the central conflict and specific stakes (what happens if they fail?).
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

CRITICAL PLOT RULES:
- Continuous Narrative: This is ONE continuous story, not an anthology. 
- The protagonist(s) introduced in Chapter 1 must be the focus of Chapter 2, 3, etc.
- Cause and Effect: The events of Chapter X must directly cause the events of Chapter X+1.

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
- {prot_min}-{prot_max} protagonists. Include: Goal, Flaw, and a specific physical mannerism/tic.
- {ant_min} antagonist with a clear opposing goal.
- {side_min}-{side_max} supporting characters. Include: Relationship to protagonist.
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
- STAGE BUSINESS: Ensure characters are doing physical tasks while interacting. No "talking heads" in a void.

PREVIOUS CHAPTER CONTINUITY (summary of what ACTUALLY happened; may be empty):
{prev_chapter_continuity}

PREVIOUS CHAPTER ENDING EXCERPT (tail of last scene; may be empty):
{prev_chapter_ending_excerpt}

{hard_rules}
{hard_rules_consistency}

Return JSON only that matches the schema.
"""

PROMPT_WRITE_BEAT = """\
You are a lead novelist for a gritty, high-stakes thriller.

### TASK
Write the prose for **Beat {beat_number}** ({beat_type}).

### CONTEXT
**PREVIOUS TEXT (Already Written):**
\"\"\"{prev_text}\"\"\"

**CURRENT BEAT PLAN:**
{beat_description}

### CRITICAL RULES (VIOLATION = FAILURE)

1.  **FORWARD MOTION (NO LOOPING):**
    * The "Previous Text" has already happened. **Do not summarize it.**
    * **Do not** re-state the last action.
    * Write what happens **1 second later**. Move the timeline forward immediately.

2.  **SENTENCE ATTACK (VARY STARTS):**
    * **BANNED:** Do NOT start the first sentence with a Proper Name (e.g., "Arin...") or Pronoun ("He...").
    * **REQUIRED:** Start the first sentence with:
        * A sound ("The click of the safety...")
        * A smell ("Ozone hung heavy...")
        * A physical sensation ("Cold metal pressed against...")
        * Dialogue ("'Get down,' he hissed...")

3.  **NEGATIVE CONSTRAINTS (BANNED WORDS):**
    * **Strictly forbidden:** "shiver down spine", "air thickened", "unseen hand", "cacophony", "labyrinthine", "neon" (use specific colors instead), "pulsing energy", "moths to a flame".
    * **No filter words:** Avoid "He saw", "She felt", "He heard". Describe the thing seen/felt/heard directly.

4.  **STAGE BUSINESS:**
    * Characters must **DO** things while talking (lighting a cigarette, checking a weapon, cleaning glasses). No "talking heads" in a void.

### OUTPUT FORMAT
Return JSON ONLY. No markdown, no pre-text.
{{"text": "..."}}
"""

PROMPT_CHAPTER_CONTINUITY = """
You are an editor creating a short continuity capsule for the next chapter planning.

Return JSON ONLY with:
{{
  "bullets": ["...", "..."]
}}

Rules:
- 10 to 20 bullets.
- Each bullet must be a concrete fact from the text (events, reveals, character state, unresolved threads).
- No speculation, no new facts.
- Keep bullets short (max ~18 words each).

CHAPTER PROSE:
{chapter_prose}
""".strip()


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
