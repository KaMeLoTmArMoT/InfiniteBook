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

Target Language: {language}
Genre: {genre}
Idea: {idea}

Guidance:
- Range: Classic -> Unexpected.
- Each variation should be a compelling book blurb in {language}.
- Highlight the central conflict and specific stakes (what happens if they fail?).
- Keep it concise, punchy, and coherent.

{hard_rules}

Return JSON only that matches the schema.
"""

PROMPT_PLOT = """\
You are a professional story architect.

Create a chapter outline for a novel.

Target Language: {language}
Title: {title}
Genre: {genre}
Premise: {description}

Structure requirements:
- {chapters_min}-{chapters_max} chapters total.
- Follow: Setup -> Inciting Incident -> Rising Action -> Climax -> Resolution.
- Each chapter must have: number, title, summary.
- All titles and summaries must be written in {language}.

CRITICAL PLOT RULES:
- Continuous Narrative: This is ONE continuous story, not an anthology. 
- The protagonist(s) introduced in Chapter 1 must be the focus of Chapter 2, 3, etc.
- Cause and Effect: The events of Chapter X must directly cause the events of Chapter X+1.

{hard_rules}

Return JSON only that matches the schema.
"""

PROMPT_CHARACTERS = """\
You are a novelist building a cast bible.

Target Language: {language}
Title: {title}
Genre: {genre}

Plot context:
{plot_summary}

Requirements:
- Output all character details (names can be native, but descriptions/goals must be in {language}).
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

Target Language: {language}
Book title: {title}
Genre: {genre}
Chapter title: {chapter_title}
Chapter summary: {chapter_summary}
Characters present: {characters_present}

Requirements:
- Produce {beats_min}-{beats_max} beats in {language}.
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

# TODO: make more stable - dialog anways in double quotes, french quotes - for self names or whatever
PROMPT_WRITE_BEAT = """\
You are a lead novelist for a gritty, high-stakes thriller.

### TASK
Write the prose for **Beat {beat_number}** ({beat_type}).

### TARGET LANGUAGE
**{language}** (All output text must be in this language).

### CONTEXT
**PREVIOUS TEXT (Already Written):**
\"\"\"{prev_text}\"\"\"

**PREVIOUS BEATS (Already Used for previous chunks):**
\"\"\"{prev_beats}\"\"\"

### CONTEXT (PREVIOUS CHAPTER — FOR CONTINUITY ONLY)
NOTE: The following context (if present) is from the PREVIOUS CHAPTER. It is NOT part of the current chapter plan.
When continuing a story across chapters, continuity must be preserved unless the current chapter plan clearly implies a time jump.

**PREVIOUS CHAPTER CONTINUITY CAPSULE (facts + open threads):**
\"\"\"{prev_chapter_capsule}\"\"\"

**PREVIOUS CHAPTER ENDING EXCERPT (tail of previous chapter prose):**
\"\"\"{prev_chapter_ending}\"\"\"

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
        * A sound
        * A smell
        * A physical sensation
        * Dialogue

3.  **NEGATIVE CONSTRAINTS (BANNED WORDS):**
    * **Strictly forbidden:** "shiver down spine", "air thickened", "unseen hand", "cacophony", "labyrinthine", "neon" (use specific colors instead), "pulsing energy", "moths to a flame".
    * **No filter words:** Avoid "He saw", "She felt", "He heard". Describe the thing seen/felt/heard directly.
    * *Note: If writing in non-English, avoid equivalent clichés in {language}.*

4.  **STAGE BUSINESS:**
    * Characters must **DO** things while talking (lighting a cigarette, checking a weapon, cleaning glasses). No "talking heads" in a void.

### PACING + LENGTH (HUMAN MIX)
- Write for a TikTok-friendly reading experience: compact, high-signal prose.
- Choose ONE length mode based on what the beat *needs* (do not announce the mode):
  * Micro: 70–120 words (fast punch-in)
  * Standard: 130–220 words (default)
  * Extended: 230–320 words (only if the beat has multiple moves or emotional turn)
- Vary paragraphing: 1–4 paragraphs. Mix short and long sentences; allow fragments.

### DIALOGUE BEHAVIOR
- If this beat is Dialogue-heavy: include 3–8 separate dialogue lines with interruptions, overlaps, and subtext.
- Otherwise: optionally inject 1–3 quick lines of dialogue if it improves realism.
- Dialogue must be grounded with physical action (stage business) while speaking.
- Dialogue language: {language}.

### OUTPUT FORMAT
Return JSON ONLY. No markdown, no pre-text.
{{"text": "..."}}
"""

PROMPT_CHAPTER_CONTINUITY = """
You are an editor creating a short continuity capsule for the next chapter planning.

Target Language: {language}

Return JSON ONLY with:
{{
  "bullets": ["...", "..."]
}}

Rules:
- 10 to 20 bullets in {language}.
- Each bullet must be a concrete fact from the text (events, reveals, character state, unresolved threads).
- No speculation, no new facts.
- Keep bullets short (max ~18 words each).

CHAPTER PROSE:
{chapter_prose}
""".strip()
