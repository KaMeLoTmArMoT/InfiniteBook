let selectedData = null;
let currentPlotData = null;
let currentCharacters = null;

let currentBeats = null;     // Step 4 beats array
let beatTexts = {};          // { idx: "text" } loaded from /api/state

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("btn-refine").addEventListener("click", refineIdea);
  document.getElementById("btn-generate-plot").addEventListener("click", generatePlot);
  document.getElementById("btn-generate-chars").addEventListener("click", generateCharacters);
  document.getElementById("btn-plan-chapter").addEventListener("click", planFirstChapter);

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

  loadStateOnStart();
  connectMonitor();
});

/* ---------------------------
   STATE LOAD (persistence)
---------------------------- */

async function loadStateOnStart() {
  try {
    const state = await fetchJSON("/api/state");

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
      document.getElementById("btn-generate-chars").disabled = false;
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
      document.getElementById("btn-plan-chapter").disabled = false;
      setStepStatus("step-3", "Loaded");
    }

    if (state.beats_ch1 && state.beats_ch1.beats) {
      currentBeats = state.beats_ch1.beats;
      document.getElementById("loader-4").style.display = "none";
      renderBeats(currentBeats);
      setStepStatus("step-4", "Loaded");
    }

    // Step 5: persisted texts
    beatTexts = normalizeBeatTextsKeys(state.beat_texts_ch1 || {});
    if (currentBeats && currentBeats.length) {
      renderWriteBeats(currentBeats, beatTexts);
      setStepStatus("step-5", "Ready");

      const btnWriteNext = document.getElementById("btn-write-next");
      if (btnWriteNext) btnWriteNext.disabled = false;

      const btnClearAll = document.getElementById("btn-clear-all");
      if (btnClearAll) btnClearAll.disabled = false;

      const btnGenAll = document.getElementById("btn-generate-all");
      if (btnGenAll) btnGenAll.disabled = false;
    }

    // Auto-open the latest available step
    if (currentBeats) openStep("step-5");
    else if (state.beats_ch1) openStep("step-4");
    else if (state.characters && (currentCharacters?.length || 0) > 0) openStep("step-3");
    else if (state.plot) openStep("step-2");
    else openStep("step-1");
  } catch (e) {
    console.warn("No persisted state or failed to load state:", e);
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

function showGeneratedText(text) {
  const out = document.getElementById("generated-text");
  if (!out) {
    alert("Missing <pre id='generated-text'> in HTML (Step 5). Add it to see generated prose.");
    return;
  }
  out.style.display = "block";
  out.textContent = text || "";
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
  document.getElementById("btn-generate-chars").disabled = true;

  try {
    const plotData = await fetchJSON("/api/plot", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(selectedData),
    });

    currentPlotData = plotData;
    renderPlot(plotData);

    setStepStatus("step-2", "Done");
    document.getElementById("btn-generate-chars").disabled = false;
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
  document.getElementById("btn-plan-chapter").disabled = true;

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
    document.getElementById("btn-plan-chapter").disabled = false;
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

    const ok = confirm("Delete this character?");
    if (!ok) return;

    try {
      btn.disabled = true;
      await fetchJSON(`/api/characters/${id}`, { method: "DELETE" });

      const st = await fetchJSON("/api/state");
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

async function planFirstChapter() {
  if (!currentPlotData || !currentPlotData.chapters || !currentPlotData.chapters.length) return;
  if (!selectedData) return;

  openStep("step-4");
  setStepStatus("step-4", "Running...");
  document.getElementById("loader-4").style.display = "block";
  document.getElementById("beats-container").style.display = "none";

  const firstChapter = currentPlotData.chapters[0];
  document.getElementById("current-chapter-title-display").innerText = `Ch 1: ${firstChapter.title}`;

  try {
    const data = await fetchJSON("/api/chapter_plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: selectedData.title,
        genre: selectedData.genre,
        chapter_title: firstChapter.title,
        chapter_summary: firstChapter.summary,
        characters: currentCharacters || [],
      }),
    });

    currentBeats = data.beats || [];
    renderBeats(currentBeats);

    // Step 5 becomes available
    renderWriteBeats(currentBeats, beatTexts);
    setStepStatus("step-5", "Ready");

    const btnWriteNext = document.getElementById("btn-write-next");
    if (btnWriteNext) btnWriteNext.disabled = false;

    const btnClearAll = document.getElementById("btn-clear-all");
    if (btnClearAll) btnClearAll.disabled = false;

    const btnGenAll = document.getElementById("btn-generate-all");
    if (btnGenAll) btnGenAll.disabled = false;

    setStepStatus("step-4", "Done");
    openStep("step-5");
  } catch (e) {
    console.error(e);
    alert("Error planning chapter");
    setStepStatus("step-4", "Error");
  } finally {
    document.getElementById("loader-4").style.display = "none";
  }
}

function renderBeats(beats) {
  document.getElementById("beats-container").style.display = "block";
  const list = document.getElementById("beats-list");
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
   STEP 5: WRITE BEATS
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

      const ok = confirm(`Clear Beat ${idx + 1} (beat_index=${idx}) and ALL next beats from DB?`);
      if (!ok) return;

      await clearFrom(idx); // <-- clears idx, idx+1, ...
      return;
    }

    const writeBtn = event.target.closest("button[data-write-beat]");
    if (writeBtn) {
      const idx = Number(writeBtn.getAttribute("data-write-beat"));
      if (Number.isNaN(idx)) return;

      const isRewrite = !!(beatTexts[idx] && beatTexts[idx].trim().length);
      if (isRewrite) {
        // auto-clear all NEXT beats (idx+1..)
        await clearFrom(idx + 1);
      }

      await writeBeat(idx);
    }
  });
}

async function clearBeat(idx) {
  const ok = confirm(`Clear generated text for Beat ${idx + 1} (beat_index=${idx})?`);
  if (!ok) return;

  await disableWriteControls(true);
  try {
    await fetchJSON("/api/beat/clear", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chapter: 1, beat_index: idx }),
    });

    delete beatTexts[idx];
    renderWriteBeats(currentBeats, beatTexts);
    setStepStatus("step-5", `Beat ${idx + 1} cleared`);
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
      body: JSON.stringify({ chapter: 1, from_beat_index: fromIdx }),
    });

    // local state: remove all >= fromIdx
    Object.keys(beatTexts).forEach((k) => {
      const i = Number(k);
      if (!Number.isNaN(i) && i >= fromIdx) delete beatTexts[i];
    });

    renderWriteBeats(currentBeats, beatTexts);
    setStepStatus("step-5", `Cleared beats from ${fromIdx + 1}`);
  } catch (e) {
    console.error(e);
    alert("Failed to clear beats in DB");
  } finally {
    await disableWriteControls(false);
  }
}

async function clearAllBeats() {
  if (!currentBeats || !currentBeats.length) return;

  const ok = confirm("Clear ALL generated beat texts? (Deletes from DB)");
  if (!ok) return;

  openStep("step-5", { scroll: false });
  setStepStatus("step-5", "Clearing all...");

  await disableWriteControls(true);
  try {
    // Clear from beat 0 onward (DB)
    await fetchJSON("/api/beat/clear_from", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chapter: 1, from_beat_index: 0 }),
    });

    // Local state
    beatTexts = {};
    renderWriteBeats(currentBeats, beatTexts);

    setStepStatus("step-5", "Cleared all");
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

  // Start from first unwritten beat
  let start = firstUnwrittenIndex();

  // If all written -> ask what to do
  if (start === null) {
    const ok = confirm("All beats already written. Clear all and regenerate from Beat 1?");
    if (!ok) return;
    await clearAllBeats();
    start = 0;
  }

  await disableWriteControls(true);

  try {
    for (let i = start; i < currentBeats.length; i++) {
      // In case something changed mid-run
      if (beatTexts[i] && beatTexts[i].trim().length) continue;

      setStepStatus("step-5", `Generating ${i + 1} / ${currentBeats.length}...`);

      // show per-beat "writing..." marker without scrolling
      const proseEl = document.getElementById(`beat-prose-${i}`);
      if (proseEl) {
        proseEl.textContent = "(writing...)";
        proseEl.style.color = "#64748b";
        proseEl.style.fontStyle = "italic";
      }

      const data = await fetchJSON(`/api/write_beat?chapter=1&beat_index=${i}`);
      const text = data.text || "";

      beatTexts[i] = text;

      // Render after each beat so user sees progress inline
      renderWriteBeats(currentBeats, beatTexts);
    }

    setStepStatus("step-5", "Generate all done");
  } catch (e) {
    console.error(e);
    alert("Generate all stopped due to an error");
    setStepStatus("step-5", "Error");
  } finally {
    await disableWriteControls(false);
  }
}

async function disableWriteControls(disabled) {
  const btnNext = document.getElementById("btn-write-next");
  if (btnNext) btnNext.disabled = disabled;

  const btnClearAll = document.getElementById("btn-clear-all");
  if (btnClearAll) btnClearAll.disabled = disabled;

  const btnGenAll = document.getElementById("btn-generate-all");
  if (btnGenAll) btnGenAll.disabled = disabled;

  document.querySelectorAll("button[data-write-beat]").forEach((b) => (b.disabled = disabled));
  document.querySelectorAll("button[data-clear-beat]").forEach((b) => (b.disabled = disabled));
  document.querySelectorAll("button[data-clear-from]").forEach((b) => (b.disabled = disabled));
}

function firstUnwrittenIndex() {
  if (!currentBeats || !currentBeats.length) return null;
  for (let i = 0; i < currentBeats.length; i++) {
    if (!beatTexts[i] || beatTexts[i].trim().length === 0) return i;
  }
  return null;
}

async function writeBeat(beatIndex) {
  if (!currentBeats || !currentBeats.length) {
    alert("No beats loaded. Run Step 4 first.");
    return;
  }

  // Optional warning: allow non-linear writing, but warn
  const nextIdx = firstUnwrittenIndex();
  if (nextIdx !== null && beatIndex > nextIdx && (!beatTexts[beatIndex] || !beatTexts[beatIndex].trim().length)) {
    const ok = confirm(
      `Beat ${nextIdx + 1} is the next unwritten beat.\n` +
      `You are trying to write Beat ${beatIndex + 1}.\n\nContinue anyway?`
    );
    if (!ok) return;
  }

  openStep("step-5", { scroll: false });
  setStepStatus("step-5", `Writing beat ${beatIndex + 1}...`);

  await disableWriteControls(true);

  // live UI feedback (show placeholder immediately)
  const proseEl = document.getElementById(`beat-prose-${beatIndex}`);
  if (proseEl) {
    proseEl.textContent = "(writing...)";
    proseEl.style.color = "#64748b";
    proseEl.style.fontStyle = "italic";
  }

  try {
    const data = await fetchJSON(`/api/write_beat?chapter=1&beat_index=${beatIndex}`);
    const text = data.text || "";

    beatTexts[beatIndex] = text;

    // Re-render so the text appears inline in that beat
    renderWriteBeats(currentBeats, beatTexts);

    // Scroll to the beat that was just written
    const row = document.getElementById(`write-beat-row-${beatIndex}`);
    // if (row) row.scrollIntoView({ behavior: "smooth", block: "start" });  # too jumpy

    setStepStatus("step-5", `Beat ${beatIndex + 1} done`);
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
  if (idx === null) {
    alert("All beats are already written. Use Rewrite on any beat.");
    return;
  }

  await writeBeat(idx);
}
