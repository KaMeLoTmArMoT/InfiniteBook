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
