let selectedData = null;
let currentPlotData = null;
let currentCharacters = null;

let currentChapter = 1;      // 1-based chapter index
let currentBeats = null;     // Step 4 beats array for current chapter
let beatTexts = {};          // { idx: "text" } for current chapter (idx is 0-based)

// Assumes these helpers exist globally (utils.js / monitor.js):
// fetchJSON, openStep, setStepStatus, enableSingleOpenAccordion, escapeHTML, connectMonitor

document.addEventListener("DOMContentLoaded", () => {
  const btnRefine = document.getElementById("btn-refine");
  if (btnRefine) btnRefine.addEventListener("click", refineIdea);

  const btnPlot = document.getElementById("btn-generate-plot");
  if (btnPlot) btnPlot.addEventListener("click", generatePlot);

  const btnChars = document.getElementById("btn-generate-chars");
  if (btnChars) btnChars.addEventListener("click", generateCharacters);

  // Step 4 plan button (IMPORTANT: scoped selector)
  const btnPlanStep4 = document.querySelector("#step-4 #btn-plan-chapter");
  if (btnPlanStep4) btnPlanStep4.addEventListener("click", planCurrentChapter);

  // Optional: Step 3 legacy button (rename in HTML to btn-plan-chapter-step3)
  const btnPlanStep3 = document.getElementById("btn-plan-chapter-step3");
  if (btnPlanStep3) {
    btnPlanStep3.addEventListener("click", async () => {
      // convenience: open step 4, ensure chapter 1 is selected, then plan
      currentChapter = 1;
      updateChapterNavButtons();
      setChapterTitleDisplay();
      updatePlanButtonUI();
      openStep("step-4", { scroll: true });
      await planCurrentChapter();
    });
  }

  enableSingleOpenAccordion();
  wireCharacterDeleteDelegation();

  // Step 5 handlers
  wireWriteBeatDelegation();

  const btnWriteNext = document.getElementById("btn-write-next");
  if (btnWriteNext) btnWriteNext.addEventListener("click", writeNextBeat);

  const btnClearAll = document.getElementById("btn-clear-all");
  if (btnClearAll) btnClearAll.addEventListener("click", clearAllBeats);

  const btnGenAll = document.getElementById("btn-generate-all");
  if (btnGenAll) btnGenAll.addEventListener("click", generateAllBeats);

  // Chapter nav (Step 5 buttons in your HTML)
  const btnPrev = document.getElementById("btn-prev-chapter");
  if (btnPrev) btnPrev.addEventListener("click", () => gotoChapter(currentChapter - 1));

  const btnNext = document.getElementById("btn-next-chapter");
  if (btnNext) btnNext.addEventListener("click", () => gotoChapter(currentChapter + 1));

  // Step 4 "Write It" button
  const btnWriteIt = document.querySelector("#step-4 #btn-write-it");
  if (btnWriteIt) btnWriteIt.addEventListener("click", () => openStep("step-5", { scroll: true }));

  loadStateOnStart();
  connectMonitor();
});

/* ---------------------------
   CHAPTER NAV
---------------------------- */

function totalChapters() {
  return (currentPlotData && currentPlotData.chapters && currentPlotData.chapters.length)
    ? currentPlotData.chapters.length
    : 0;
}

function updateChapterNavButtons() {
  const total = totalChapters();

  const btnPrev = document.getElementById("btn-prev-chapter");
  const btnNext = document.getElementById("btn-next-chapter");

  if (btnPrev) btnPrev.disabled = !(total > 0 && currentChapter > 1);
  if (btnNext) btnNext.disabled = !(total > 0 && currentChapter < total);
}

function setChapterTitleDisplay() {
  const el = document.getElementById("current-chapter-title-display");
  if (!el) return;

  const ch = currentPlotData?.chapters?.[currentChapter - 1];
  el.innerText = ch ? `Ch ${currentChapter}: ${ch.title}` : `Ch ${currentChapter}`;
}

async function gotoChapter(chapterNum) {
  const total = totalChapters();
  if (total <= 0) return;
  if (chapterNum < 1 || chapterNum > total) return;

  currentChapter = chapterNum;
  updateChapterNavButtons();
  setChapterTitleDisplay();

  // While loading, show Step 4 (so user sees chapter changed)
  showStep4Container();
  setStepStatus("step-4", `Loading (Ch ${currentChapter})...`);
  updatePlanButtonUI();

  await loadChapterState(currentChapter, { open: true });
}

function enableStep5Buttons(enabled) {
  const btnWriteNext = document.getElementById("btn-write-next");
  if (btnWriteNext) btnWriteNext.disabled = !enabled;

  const btnClearAll = document.getElementById("btn-clear-all");
  if (btnClearAll) btnClearAll.disabled = !enabled;

  const btnGenAll = document.getElementById("btn-generate-all");
  if (btnGenAll) btnGenAll.disabled = !enabled;
}

function enableWriteIt(enabled) {
  const btnWriteIt = document.querySelector("#step-4 #btn-write-it");
  if (btnWriteIt) btnWriteIt.disabled = !enabled;
}

/* ---------------------------
   STEP 4 CONTAINER VISIBILITY
---------------------------- */

function showStep4Container() {
  const loader = document.getElementById("loader-4");
  const container = document.getElementById("beats-container");
  if (loader) loader.style.display = "none";
  if (container) container.style.display = "block";
}

/* ---------------------------
   STEP 4 PLAN BUTTON UI
---------------------------- */

function hasBeatsPlanLoaded() {
  return !!(currentBeats && currentBeats.length);
}

function updatePlanButtonUI() {
  // IMPORTANT: scope to Step 4 so duplicate IDs can't break it
  const btn = document.querySelector("#step-4 #btn-plan-chapter");
  const hint = document.getElementById("step-4-plan-hint");

  const canPlan = !!(selectedData && currentPlotData && currentPlotData.chapters && currentPlotData.chapters.length);

  if (btn) {
    btn.disabled = !canPlan;
    btn.innerText = hasBeatsPlanLoaded() ? "Regenerate plan" : "Generate plan";
  }

  if (hint) {
    hint.innerText = hasBeatsPlanLoaded()
      ? `Plan loaded (Ch ${currentChapter}).`
      : `No plan (Ch ${currentChapter}). Click “Generate plan”.`;
  }

  enableWriteIt(hasBeatsPlanLoaded());
  setStepStatus("step-4", hasBeatsPlanLoaded() ? `Loaded (Ch ${currentChapter})` : `No plan (Ch ${currentChapter})`);
}

/* ---------------------------
   STATE LOAD (persistence)
---------------------------- */

async function loadChapterState(chapterNum, { open = false } = {}) {
  const state = await fetchJSON(`/api/state?chapter=${chapterNum}`);

  // Make sure Step 4 UI is visible even if there is no plan yet
  showStep4Container();
  setChapterTitleDisplay();

  // beats plan for this chapter
  if (state.beats && state.beats.beats) {
    currentBeats = state.beats.beats;
    renderBeats(currentBeats);

    beatTexts = normalizeBeatTextsKeys(state.beat_texts || {});
    renderWriteBeats(currentBeats, beatTexts);

    enableStep5Buttons(true);
    updatePlanButtonUI();

    if (open) openStep("step-5", { scroll: false });
    return;
  }

  // No beats plan yet for this chapter
  currentBeats = null;
  beatTexts = {};

  const beatsList = document.getElementById("beats-list");
  if (beatsList) beatsList.innerHTML = "";

  const writeList = document.getElementById("write-beats-list");
  if (writeList) writeList.innerHTML = "";

  enableStep5Buttons(false);
  updatePlanButtonUI();

  if (open) openStep("step-4", { scroll: false });
}

async function loadStateOnStart() {
  try {
    const state = await fetchJSON(`/api/state?chapter=${currentChapter}`);
    if (typeof state.chapter === "number") currentChapter = state.chapter;

    if (state.selected) {
      selectedData = state.selected;
      if (typeof state.selected.genre === "string") document.getElementById("genre").value = state.selected.genre;
      if (typeof state.selected.description === "string") document.getElementById("idea").value = state.selected.description;
      setStepStatus("step-1", "Loaded");
    }

    if (state.plot) {
      currentPlotData = state.plot;
      document.getElementById("loader-2").style.display = "none";
      renderPlot(state.plot);

      const btnChars = document.getElementById("btn-generate-chars");
      if (btnChars) btnChars.disabled = false;

      setStepStatus("step-2", "Loaded");
    }

    if (state.characters) {
      renderCharacters(state.characters);
      currentCharacters = [
        ...(state.characters.protagonists || []),
        ...(state.characters.antagonists || []),
        ...(state.characters.supporting || []),
      ];

      document.getElementById("loader-3").style.display = "none";
      document.getElementById("chars-container").style.display = "block";
      setStepStatus("step-3", "Loaded");
    }

    updateChapterNavButtons();
    setChapterTitleDisplay();
    showStep4Container();

    // chapter-specific beats + texts
    if (state.beats && state.beats.beats) {
      currentBeats = state.beats.beats;
      renderBeats(currentBeats);

      beatTexts = normalizeBeatTextsKeys(state.beat_texts || {});
      renderWriteBeats(currentBeats, beatTexts);

      setStepStatus("step-4", `Loaded (Ch ${currentChapter})`);
      setStepStatus("step-5", `Ready (Ch ${currentChapter})`);
      enableStep5Buttons(true);
    } else {
      enableStep5Buttons(false);
    }

    updatePlanButtonUI();

    if (currentBeats) openStep("step-5");
    else if (state.characters && (currentCharacters?.length || 0) > 0) openStep("step-3");
    else if (state.plot) openStep("step-2");
    else openStep("step-1");
  } catch (e) {
    console.warn("No persisted state or failed to load state:", e);
    updateChapterNavButtons();
    setChapterTitleDisplay();
    showStep4Container();
    updatePlanButtonUI();
  }
}

function normalizeBeatTextsKeys(obj) {
  const out = {};
  for (const [k, v] of Object.entries(obj || {})) {
    const idx = Number(k);
    if (!Number.isNaN(idx) && typeof v === "string") out[idx] = v;
  }
  return out;
}

function firstUnwrittenIndex() {
  if (!currentBeats || !currentBeats.length) return null;
  for (let i = 0; i < currentBeats.length; i++) {
    if (!beatTexts[i] || beatTexts[i].trim().length === 0) return i;
  }
  return null;
}

/* ---------------------------
   STEP 1: REFINE IDEA
---------------------------- */

async function refineIdea() {
  const genre = document.getElementById("genre").value.trim();
  const idea = document.getElementById("idea").value.trim();

  const btn = document.getElementById("btn-refine");
  const loader = document.getElementById("loader-1");
  const grid = document.getElementById("variations-grid");

  document.getElementById("confirm-idea-area").style.display = "none";
  selectedData = null;

  loader.style.display = "block";
  grid.innerHTML = "";
  btn.disabled = true;

  try {
    const data = await fetchJSON("/api/refine", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ genre, idea }),
    });

    renderVariations(data.options);
    setStepStatus("step-1", "Done (select one)");
  } catch (e) {
    console.error(e);
    alert("Error connecting to server");
    setStepStatus("step-1", "Error");
  } finally {
    loader.style.display = "none";
    btn.disabled = false;
  }
}

function renderVariations(options) {
  const grid = document.getElementById("variations-grid");
  grid.innerHTML = "";

  options.forEach((opt) => {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `<h3>${opt.title}</h3><div class="desc">${opt.description}</div>`;

    card.addEventListener("click", () => {
      document.querySelectorAll(".card").forEach((c) => c.classList.remove("selected"));
      card.classList.add("selected");
      selectedData = opt;

      document.getElementById("confirm-idea-area").style.display = "block";
      setStepStatus("step-1", "Selected");
      openStep("step-1");
      updatePlanButtonUI();
    });

    grid.appendChild(card);
  });
}

/* ---------------------------
   STEP 2: GENERATE PLOT
---------------------------- */

async function generatePlot() {
  if (!selectedData) return;

  openStep("step-2");
  setStepStatus("step-2", "Running...");
  document.getElementById("loader-2").style.display = "block";
  document.getElementById("plot-content").style.display = "none";

  const btnChars = document.getElementById("btn-generate-chars");
  if (btnChars) btnChars.disabled = true;

  try {
    const plotData = await fetchJSON("/api/plot", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(selectedData),
    });

    currentPlotData = plotData;
    renderPlot(plotData);

    currentChapter = 1;
    updateChapterNavButtons();
    setChapterTitleDisplay();
    showStep4Container();

    setStepStatus("step-2", "Done");
    if (btnChars) btnChars.disabled = false;

    updatePlanButtonUI();
  } catch (e) {
    console.error(e);
    alert("Error generating plot");
    setStepStatus("step-2", "Error");
  } finally {
    document.getElementById("loader-2").style.display = "none";
  }
}

function renderPlot(data) {
  const container = document.getElementById("plot-content");
  container.style.display = "block";

  let html = `<p style="font-style:italic; margin-bottom:20px;">${data.structure_analysis || ""}</p>`;
  (data.chapters || []).forEach((ch) => {
    html += `
      <div class="chapter-item">
        <div class="ch-title">Chapter ${ch.number}: ${ch.title}</div>
        <div class="ch-summary">${ch.summary}</div>
      </div>
    `;
  });

  container.innerHTML = html;
}

/* ---------------------------
   STEP 3: CHARACTERS
---------------------------- */

async function generateCharacters() {
  if (!currentPlotData || !selectedData) return;

  openStep("step-3");
  setStepStatus("step-3", "Running...");
  document.getElementById("loader-3").style.display = "block";
  document.getElementById("chars-container").style.display = "none";

  const summary = (currentPlotData.chapters || []).map((c) => `Ch${c.number}: ${c.summary}`).join("\n");

  try {
    const data = await fetchJSON("/api/characters", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: selectedData.title,
        genre: selectedData.genre,
        plot_summary: summary,
      }),
    });

    currentCharacters = [...(data.protagonists || []), ...(data.antagonists || []), ...(data.supporting || [])];
    renderCharacters(data);

    setStepStatus("step-3", "Done");
    updatePlanButtonUI();
  } catch (e) {
    console.error(e);
    alert("Error generating characters");
    setStepStatus("step-3", "Error");
  } finally {
    document.getElementById("loader-3").style.display = "none";
  }
}

function renderCharacters(data) {
  document.getElementById("chars-container").style.display = "block";

  const createCard = (char) => `
    <div class="card" style="cursor:default;">
      <div style="display:flex; justify-content:space-between; gap:10px; align-items:flex-start;">
        <h3 style="margin:0;">${char.name}</h3>
        ${
          char.id
            ? `<button class="mini-danger" data-char-id="${char.id}">Delete</button>`
            : `<button class="mini-danger" disabled title="No id yet (load from /api/state)">Delete</button>`
        }
      </div>
      <div class="tag">${char.role}</div>
      <div class="desc">${char.bio}</div>
    </div>
  `;

  document.getElementById("protagonists-grid").innerHTML =
    (data.protagonists || []).map(createCard).join("");
  document.getElementById("antagonists-grid").innerHTML =
    (data.antagonists || []).map(createCard).join("");
  document.getElementById("supporting-grid").innerHTML =
    (data.supporting || []).map(createCard).join("");
}

function wireCharacterDeleteDelegation() {
  const container = document.getElementById("chars-container");
  if (!container) return;

  container.addEventListener("click", async (event) => {
    const btn = event.target.closest("button[data-char-id]");
    if (!btn) return;

    const id = btn.getAttribute("data-char-id");
    if (!id) return;

    try {
      btn.disabled = true;
      await fetchJSON(`/api/characters/${id}`, { method: "DELETE" });

      const st = await fetchJSON(`/api/state?chapter=${currentChapter}`);
      if (st.characters) {
        renderCharacters(st.characters);
        currentCharacters = [
          ...(st.characters.protagonists || []),
          ...(st.characters.antagonists || []),
          ...(st.characters.supporting || []),
        ];
      }
    } catch (e) {
      console.error(e);
      alert("Failed to delete character");
    } finally {
      btn.disabled = false;
    }
  });
}

/* ---------------------------
   STEP 4: CHAPTER PLAN
---------------------------- */

async function planCurrentChapter() {
  if (!currentPlotData || !currentPlotData.chapters || !currentPlotData.chapters.length) return;
  if (!selectedData) return;

  const ch = currentPlotData.chapters[currentChapter - 1];
  if (!ch) return;

  openStep("step-4", { scroll: false });
  setStepStatus("step-4", `Running (Ch ${currentChapter})...`);

  const loader = document.getElementById("loader-4");
  if (loader) loader.style.display = "block";

  const container = document.getElementById("beats-container");
  if (container) container.style.display = "none";

  enableStep5Buttons(false);
  enableWriteIt(false);

  setChapterTitleDisplay();

  try {
    const data = await fetchJSON("/api/chapter_plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chapter: currentChapter,
        title: selectedData.title,
        genre: selectedData.genre,
        chapter_title: ch.title,
        chapter_summary: ch.summary,
        characters: currentCharacters || [],
      }),
    });

    currentBeats = data.beats || [];

    // Keep plan/prose consistent: wipe chapter prose in DB after (re)planning (no popup)
    try {
      await fetchJSON("/api/beat/clear_from", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chapter: currentChapter, from_beat_index: 0 }),
      });
    } catch (e) {
      console.warn("Failed to clear prose after planning (non-fatal):", e);
    }

    beatTexts = {};

    if (loader) loader.style.display = "none";
    if (container) container.style.display = "block";

    renderBeats(currentBeats);
    renderWriteBeats(currentBeats, beatTexts);

    setStepStatus("step-4", `Done (Ch ${currentChapter})`);
    setStepStatus("step-5", `Ready (Ch ${currentChapter})`);

    enableStep5Buttons(true);
    enableWriteIt(true);
    updatePlanButtonUI();

    openStep("step-5", { scroll: false });
  } catch (e) {
    console.error(e);
    alert("Error planning chapter");
    setStepStatus("step-4", "Error");
  } finally {
    if (loader) loader.style.display = "none";
    if (container) container.style.display = "block";
    updatePlanButtonUI();
  }
}

function renderBeats(beats) {
  const bc = document.getElementById("beats-container");
  if (bc) bc.style.display = "block";

  const list = document.getElementById("beats-list");
  if (!list) return;

  list.innerHTML = "";

  beats.forEach((beat) => {
    let typeClass = "type-description";
    const t = (beat.type || "").toLowerCase();
    if (t.includes("dialogue")) typeClass = "type-dialogue";
    if (t.includes("action")) typeClass = "type-action";
    if (t.includes("monologue") || t.includes("internal")) typeClass = "type-internal";

    list.innerHTML += `
      <div class="beat-item">
        <div class="beat-type ${typeClass}">${beat.type}</div>
        <div class="beat-desc">${beat.description}</div>
      </div>
    `;
  });
}

/* ---------------------------
   STEP 5: WRITE BEATS (chapter-scoped)
---------------------------- */

function renderWriteBeats(beats, textsByIdx) {
  const wrap = document.getElementById("write-beats-list");
  if (!wrap) return;

  wrap.innerHTML = "";

  beats.forEach((beat, idx) => {
    const txt = textsByIdx?.[idx] || "";
    const isWritten = txt.trim().length > 0;
    const safeText = escapeHTML(txt);

    wrap.innerHTML += `
      <div class="beat-item" id="write-beat-row-${idx}">
        <div style="display:flex; flex-direction:column; gap:6px; min-width:180px;">
          <div style="font-weight:700;">Beat ${idx + 1}</div>

          <div style="font-size:0.85rem; color:${isWritten ? "#16a34a" : "#64748b"};">
            ${isWritten ? "Written" : "Not written"}
          </div>

          <button data-write-beat="${idx}" style="background:#6366f1;">
            ${isWritten ? "Rewrite" : "Write"}
          </button>

          ${isWritten ? `<button data-clear-beat="${idx}" style="background:#ef4444;">Clear</button>` : ""}
          ${isWritten ? `<button data-clear-from="${idx}" style="background:#b91c1c;">Clear from here</button>` : ""}
        </div>

        <div class="beat-desc" style="width:100%;">
          <div style="font-weight:700; margin-bottom:6px;">${beat.type}</div>
          <div style="margin-bottom:10px;">${beat.description}</div>

          <div style="margin-top:10px; border-top:1px solid #e2e8f0; padding-top:10px;">
            <div style="font-weight:700; color:#334155; margin-bottom:6px;">
              Generated text
            </div>

            ${
              isWritten
                ? `<pre id="beat-prose-${idx}" style="white-space:pre-wrap; margin:0; padding:10px; background:#0b1220; color:#e2e8f0; border-radius:8px;">${safeText}</pre>`
                : `<div id="beat-prose-${idx}" style="color:#64748b; font-style:italic;">(not written yet)</div>`
            }
          </div>
        </div>
      </div>
    `;
  });
}

function wireWriteBeatDelegation() {
  const wrap = document.getElementById("write-beats-list");
  if (!wrap) return;

  wrap.addEventListener("click", async (event) => {
    const clearBtn = event.target.closest("button[data-clear-beat]");
    if (clearBtn) {
      const idx = Number(clearBtn.getAttribute("data-clear-beat"));
      if (Number.isNaN(idx)) return;
      await clearBeat(idx);
      return;
    }

    const clearFromBtn = event.target.closest("button[data-clear-from]");
    if (clearFromBtn) {
      const idx = Number(clearFromBtn.getAttribute("data-clear-from"));
      if (Number.isNaN(idx)) return;
      await clearFrom(idx);
      return;
    }

    const writeBtn = event.target.closest("button[data-write-beat]");
    if (writeBtn) {
      const idx = Number(writeBtn.getAttribute("data-write-beat"));
      if (Number.isNaN(idx)) return;

      const isRewrite = !!(beatTexts[idx] && beatTexts[idx].trim().length);
      if (isRewrite) {
        // auto-clear all NEXT beats (idx+1..) with no popup
        await clearFrom(idx + 1);
      }

      await writeBeat(idx);
    }
  });
}

async function clearBeat(idx) {
  await disableWriteControls(true);
  try {
    await fetchJSON("/api/beat/clear", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chapter: currentChapter, beat_index: idx }),
    });

    delete beatTexts[idx];
    renderWriteBeats(currentBeats, beatTexts);
    setStepStatus("step-5", `Beat ${idx + 1} cleared (Ch ${currentChapter})`);
  } catch (e) {
    console.error(e);
    alert("Failed to clear beat in DB");
  } finally {
    await disableWriteControls(false);
  }
}

async function clearFrom(fromIdx) {
  await disableWriteControls(true);
  try {
    await fetchJSON("/api/beat/clear_from", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chapter: currentChapter, from_beat_index: fromIdx }),
    });

    Object.keys(beatTexts).forEach((k) => {
      const i = Number(k);
      if (!Number.isNaN(i) && i >= fromIdx) delete beatTexts[i];
    });

    renderWriteBeats(currentBeats, beatTexts);
    setStepStatus("step-5", `Cleared from beat ${fromIdx + 1} (Ch ${currentChapter})`);
  } catch (e) {
    console.error(e);
    alert("Failed to clear beats in DB");
  } finally {
    await disableWriteControls(false);
  }
}

async function clearAllBeats() {
  if (!currentBeats || !currentBeats.length) return;

  openStep("step-5", { scroll: false });
  setStepStatus("step-5", `Clearing all (Ch ${currentChapter})...`);

  await disableWriteControls(true);
  try {
    await fetchJSON("/api/beat/clear_from", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chapter: currentChapter, from_beat_index: 0 }),
    });

    beatTexts = {};
    renderWriteBeats(currentBeats, beatTexts);

    setStepStatus("step-5", `Cleared all (Ch ${currentChapter})`);
  } catch (e) {
    console.error(e);
    alert("Failed to clear all beats in DB");
    setStepStatus("step-5", "Error");
  } finally {
    await disableWriteControls(false);
  }
}

async function generateAllBeats() {
  if (!currentBeats || !currentBeats.length) return;

  openStep("step-5", { scroll: false });

  let start = firstUnwrittenIndex();
  if (start === null) {
    // no popup: just clear and regenerate
    await clearAllBeats();
    start = 0;
  }

  await disableWriteControls(true);
  try {
    for (let i = start; i < currentBeats.length; i++) {
      if (beatTexts[i] && beatTexts[i].trim().length) continue;

      setStepStatus("step-5", `Generating ${i + 1} / ${currentBeats.length} (Ch ${currentChapter})...`);

      const proseEl = document.getElementById(`beat-prose-${i}`);
      if (proseEl) {
        proseEl.textContent = "(writing...)";
        proseEl.style.color = "#64748b";
        proseEl.style.fontStyle = "italic";
      }

      const data = await fetchJSON(`/api/write_beat?chapter=${currentChapter}&beat_index=${i}`);
      const text = data.text || "";

      beatTexts[i] = text;
      renderWriteBeats(currentBeats, beatTexts);
    }

    setStepStatus("step-5", `Generate all done (Ch ${currentChapter})`);
  } catch (e) {
    console.error(e);
    alert("Generate all stopped due to an error");
    setStepStatus("step-5", "Error");
  } finally {
    await disableWriteControls(false);
  }
}

async function disableWriteControls(disabled) {
  enableStep5Buttons(!disabled);

  const btnPrev = document.getElementById("btn-prev-chapter");
  const btnNext = document.getElementById("btn-next-chapter");

  if (btnPrev) btnPrev.disabled = disabled || !(totalChapters() > 0 && currentChapter > 1);
  if (btnNext) btnNext.disabled = disabled || !(totalChapters() > 0 && currentChapter < totalChapters());

  document.querySelectorAll("button[data-write-beat]").forEach((b) => (b.disabled = disabled));
  document.querySelectorAll("button[data-clear-beat]").forEach((b) => (b.disabled = disabled));
  document.querySelectorAll("button[data-clear-from]").forEach((b) => (b.disabled = disabled));
}

async function writeBeat(beatIndex) {
  if (!currentBeats || !currentBeats.length) {
    alert("No beats loaded. Run Step 4 first.");
    return;
  }

  openStep("step-5", { scroll: false });
  setStepStatus("step-5", `Writing beat ${beatIndex + 1} (Ch ${currentChapter})...`);

  await disableWriteControls(true);

  const proseEl = document.getElementById(`beat-prose-${beatIndex}`);
  if (proseEl) {
    proseEl.textContent = "(writing...)";
    proseEl.style.color = "#64748b";
    proseEl.style.fontStyle = "italic";
  }

  try {
    const data = await fetchJSON(`/api/write_beat?chapter=${currentChapter}&beat_index=${beatIndex}`);
    const text = data.text || "";

    beatTexts[beatIndex] = text;
    renderWriteBeats(currentBeats, beatTexts);

    setStepStatus("step-5", `Beat ${beatIndex + 1} done (Ch ${currentChapter})`);
  } catch (e) {
    console.error(e);
    alert("Failed to write beat");
    setStepStatus("step-5", "Error");
  } finally {
    await disableWriteControls(false);
  }
}

async function writeNextBeat() {
  if (!currentBeats || !currentBeats.length) return;

  const idx = firstUnwrittenIndex();
  if (idx === null) return;

  await writeBeat(idx);
}
