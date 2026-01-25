/* ========= Project ========= */
let projectId = localStorage.getItem("ib_project_id") || null;

function api(path) {
  if (!projectId) throw new Error("projectId not set");
  return `/api/projects/${projectId}${path}`;
}

async function ensureProject() {
  if (projectId) return projectId;

  const res = await fetchJSON("/api/projects");
  const items = res?.items || [];

  if (items.length) {
    projectId = items[0].id;
  } else {
    const created = await fetchJSON("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "Untitled" }),
    });
    projectId = created?.project?.id;
  }

  if (!projectId) throw new Error("Failed to init project");
  localStorage.setItem("ib_project_id", projectId);
  return projectId;
}

/* ========= Tiny helpers ========= */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const on = (sel, evt, fn, root = document) => {
  const el = $(sel, root);
  if (el) el.addEventListener(evt, fn);
  return el;
};
const show = (sel, yes, root = document) => {
  const el = $(sel, root);
  if (el) el.style.display = yes ? "block" : "none";
};
const setDisabled = (sel, disabled, root = document) => {
  const el = $(sel, root);
  if (el) el.disabled = !!disabled;
};
const setDisabledMany = (sels, disabled, root = document) => sels.forEach((s) => setDisabled(s, disabled, root));

/* ========= State ========= */
let selectedData = null;
let currentPlotData = null;
let currentCharacters = null;

let currentChapter = 1;      // 1-based
let currentBeats = null;     // beats array for current chapter
let beatTexts = {};          // { idx: text } for current chapter (0-based)

// =======================
// AUDIO UI v2 (multi TTS)
// =======================

const TTS_PROVIDERS = [
  { key: "piper", label: "Piper" },
  { key: "xtts", label: "XTTS" },
  { key: "qwen", label: "Qwen" },
];

// beatAudio[idx][provider] = { exists, status, url }
let beatAudio = {};

function getActiveTtsProvider() {
  const el = $("#tts-providers");
  const raw = (el?.textContent || "").toLowerCase();

  // Look for the first known provider name anywhere in the text
  const known = ["piper", "xtts", "qwen"];
  for (const k of known) {
    if (raw.includes(k)) return k;
  }
  return null;
}

function getBeatAudio(idx, provider) {
  if (!beatAudio[idx]) beatAudio[idx] = {};
  if (!beatAudio[idx][provider]) {
    beatAudio[idx][provider] = { exists: false, status: "missing", url: "" };
  }
  return beatAudio[idx][provider];
}

function setBeatAudioStatus(idx, provider, status, patch = {}) {
  if (!beatAudio[idx]) beatAudio[idx] = {};
  beatAudio[idx][provider] = { ...getBeatAudio(idx, provider), ...patch, status };
  updateBeatAudioRowUI(idx);
}

function updateBeatAudioRowUI(idx) {
  const row = $(`#write-beat-row-${idx}`);
  if (!row) return;

  const active = getActiveTtsProvider();

  TTS_PROVIDERS.forEach((p) => {
    const st = getBeatAudio(idx, p.key);

    const genBtn = $(`button[data-audio-generate="${idx}"][data-tts-provider="${p.key}"]`, row);
    const stEl = $(`span[data-audio-status="${idx}"][data-tts-provider="${p.key}"]`, row);
    const audioEl = $(`audio[data-audio-el="${idx}"][data-tts-provider="${p.key}"]`, row);

    if (genBtn) {
      genBtn.textContent = st.exists ? "Regenerate" : "Generate";
      genBtn.disabled = !(active && active === p.key);
    }

    // If audio exists: show only audio (no "ready" label)
    if (stEl) {
      if (st.exists) {
        stEl.style.display = "none";
      } else {
        stEl.style.display = "inline";
        stEl.textContent = st.status || "missing";
      }
    }

    if (audioEl) {
      const hasAudio = !!(st.exists && st.url);
      audioEl.style.display = hasAudio ? "block" : "none";
      if (hasAudio && audioEl.src !== st.url) audioEl.src = st.url;
    }
  });
}

window.onTtsProvidersChanged = function () {
  // re-enable/disable Generate buttons based on newly-known active provider
  if (!currentBeats?.length) return;
  currentBeats.forEach((_, idx) => updateBeatAudioRowUI(idx));
};

/* ========= Boot ========= */
document.addEventListener("DOMContentLoaded", () => {
  on("#btn-refine", "click", refineIdea);
  on("#btn-generate-plot", "click", generatePlot);
  on("#btn-generate-chars", "click", generateCharacters);

  // Step 4 plan button (scoped => immune to duplicate IDs)
  on("#step-4 #btn-plan-chapter", "click", planCurrentChapter);

  // Optional legacy Step 3 button (if present)
  on("#btn-plan-chapter-step3", "click", async () => {
    currentChapter = 1;
    syncChapterUI();
    openStep("step-4", { scroll: true });
    await planCurrentChapter();
  });

  on("#btn-write-next", "click", writeNextBeat);
  on("#btn-clear-all", "click", clearAllBeats);
  on("#btn-generate-all", "click", generateAllBeats);

  on("#btn-prev-chapter-step4", "click", () => gotoChapter(currentChapter - 1));
  on("#btn-next-chapter-step4", "click", () => gotoChapter(currentChapter + 1));

  on("#btn-prev-chapter", "click", () => gotoChapter(currentChapter - 1));
  on("#btn-next-chapter", "click", () => gotoChapter(currentChapter + 1));

  on("#step-4 #btn-write-it", "click", () => openStep("step-5", { scroll: true }));

  enableSingleOpenAccordion();
  wireCharacterDeleteDelegation();
  wireWriteBeatDelegation();

  loadStateOnStart();
  connectMonitor();
});

/* ========= UI helpers ========= */
function totalChapters() {
  return currentPlotData?.chapters?.length || 0;
}

function setChapterTitleDisplay() {
  const ch = currentPlotData?.chapters?.[currentChapter - 1];
  const el = $("#current-chapter-title-display");
  if (el) el.innerText = ch ? `Ch ${currentChapter}: ${ch.title}` : `Ch ${currentChapter}`;
}

function showStep4Container() {
  show("#loader-4", false);
  show("#beats-container", true);
}

function hasBeatsPlanLoaded() {
  return !!(currentBeats && currentBeats.length);
}

function setStep5Enabled(enabled) {
  setDisabledMany(["#btn-write-next", "#btn-generate-all", "#btn-clear-all"], !enabled);
}

function setChapterNavEnabled(enabled) {
  const total = totalChapters();
  const canPrev = enabled && total > 0 && currentChapter > 1;
  const canNext = enabled && total > 0 && currentChapter < total;

  setDisabled("#btn-prev-chapter", !canPrev);
  setDisabled("#btn-next-chapter", !canNext);
  setDisabled("#btn-prev-chapter-step4", !canPrev);
  setDisabled("#btn-next-chapter-step4", !canNext);
}

function enableWriteIt(enabled) {
  setDisabled("#step-4 #btn-write-it", !enabled);
}

function updatePlanButtonUI() {
  const canPlan = !!(selectedData && currentPlotData?.chapters?.length);
  const btn = $("#step-4 #btn-plan-chapter");
  const hint = $("#step-4-plan-hint");

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

function syncChapterUI() {
  setChapterTitleDisplay();
  setStep5ChapterHeader();
  setChapterNavEnabled(true);
  updatePlanButtonUI();
}

/* ========= Persistence ========= */
async function loadChapterState(chapterNum, { open = false } = {}) {
  await ensureProject();

  const state = await fetchJSON(`${api(`/state?chapter=${chapterNum}`)}`);

  showStep4Container();
  setChapterTitleDisplay();
  setStep5ChapterHeader();

  if (state.beats?.beats) {
    currentBeats = state.beats.beats;
    renderBeats(currentBeats);

    beatTexts = normalizeBeatTextsKeys(state.beat_texts || {});
    beatAudio = {};
    await refreshAudioStatusForChapter(chapterNum);

    // Re-render so audio elements appear when audio exists
    renderWriteBeats(currentBeats, beatTexts);

    setStep5Enabled(true);
    updatePlanButtonUI();

    if (open) openStep("step-5", { scroll: false });
    return;
  }

  // no plan
  currentBeats = null;
  beatTexts = {};
  if ($("#beats-list")) $("#beats-list").innerHTML = "";
  if ($("#write-beats-list")) $("#write-beats-list").innerHTML = "";

  setStep5Enabled(false);
  updatePlanButtonUI();

  if (open) openStep("step-4", { scroll: false });
}

async function loadStateOnStart() {
  try {
    await ensureProject();

    const state = await fetchJSON(`${api(`/state?chapter=${currentChapter}`)}`);
    if (typeof state.chapter === "number") currentChapter = state.chapter;

    setStep5ChapterHeader();

    if (state.selected) {
      selectedData = state.selected;
      if (typeof state.selected.genre === "string") $("#genre").value = state.selected.genre;
      if (typeof state.selected.description === "string") $("#idea").value = state.selected.description;
      setStepStatus("step-1", "Loaded");
    }

    if (state.plot) {
      currentPlotData = state.plot;
      show("#loader-2", false);
      renderPlot(state.plot);
      setDisabled("#btn-generate-chars", false);
      setStepStatus("step-2", "Loaded");
    }

    if (state.characters) {
      renderCharacters(state.characters);
      currentCharacters = [
        ...(state.characters.protagonists || []),
        ...(state.characters.antagonists || []),
        ...(state.characters.supporting || []),
      ];
      show("#loader-3", false);
      show("#chars-container", true);
      setStepStatus("step-3", "Loaded");
    }

    showStep4Container();
    syncChapterUI();

    if (state.beats?.beats) {
      currentBeats = state.beats.beats;
      renderBeats(currentBeats);

      beatTexts = normalizeBeatTextsKeys(state.beat_texts || {});
      beatAudio = {};
      await refreshAudioStatusForChapter(currentChapter);

      renderWriteBeats(currentBeats, beatTexts);

      setStep5Enabled(true);
      setStepStatus("step-5", "Ready");
    } else {
      setStep5Enabled(false);
    }

    updatePlanButtonUI();

    if (currentBeats) openStep("step-5");
    else if (state.characters && (currentCharacters?.length || 0) > 0) openStep("step-3");
    else if (state.plot) openStep("step-2");
    else openStep("step-1");
  } catch (e) {
    console.warn("Failed to load state:", e);
    showStep4Container();
    syncChapterUI();
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
  if (!currentBeats?.length) return null;
  for (let i = 0; i < currentBeats.length; i++) {
    if (!beatTexts[i] || beatTexts[i].trim().length === 0) return i;
  }
  return null;
}

async function refreshAudioStatusForChapter(chapterNum) {
  if (!currentBeats?.length) return;
  await ensureProject();

  // Ensure defaults exist for every beat/provider
  currentBeats.forEach((_, idx) => {
    TTS_PROVIDERS.forEach((p) => getBeatAudio(idx, p.key));
  });

  const res = await fetchJSON(api(`/audio/status?chapter=${chapterNum}`));
  const items = res?.items || [];

  // If any item transitions missing->exists, we must re-render to create <audio> nodes
  let needRerender = false;

  items.forEach((it) => {
    const idx = Number(it.beat_index);
    if (Number.isNaN(idx)) return;

    const provider = (it.provider || it.tts_provider || "").toLowerCase();
    if (!provider) return;

    const rel =
      it.url ||
      (it.exists ? api(`/audio/wav?chapter=${chapterNum}&beat_index=${idx}&provider=${provider}`) : "");
    const abs = rel ? new URL(rel, window.location.href).href : "";

    const prev = getBeatAudio(idx, provider);
    const nextExists = !!it.exists;

    if (!prev.exists && nextExists) needRerender = true;

    beatAudio[idx][provider] = {
      exists: nextExists,
      status: it.status || (nextExists ? "ready" : "missing"),
      url: abs,
    };
  });

  if (needRerender) {
    renderWriteBeats(currentBeats, beatTexts);
    return;
  }

  currentBeats.forEach((_, idx) => updateBeatAudioRowUI(idx));
}

let _audioPollTimer = null;
let _audioPollInFlight = false;
let _audioPollChapter = null;

function stopAudioPoll() {
  if (_audioPollTimer) clearInterval(_audioPollTimer);
  _audioPollTimer = null;
  _audioPollChapter = null;
}

function startAudioPoll(chapterNum) {
  // already polling this chapter
  if (_audioPollTimer && _audioPollChapter === chapterNum) return;

  stopAudioPoll();
  _audioPollChapter = chapterNum;

  _audioPollTimer = setInterval(async () => {
    if (_audioPollInFlight) return;
    _audioPollInFlight = true;
    try {
      await refreshAudioStatusForChapter(chapterNum);

      // stop when nothing is generating
      const stillGenerating = Object.values(beatAudio).some((perBeat) =>
        Object.values(perBeat || {}).some((st) => st?.status === "generating")
      );
      if (!stillGenerating) stopAudioPoll();
    } finally {
      _audioPollInFlight = false;
    }
  }, 3000);
}

/* ========= Chapter navigation ========= */
async function gotoChapter(chapterNum) {
  const total = totalChapters();
  if (total <= 0 || chapterNum < 1 || chapterNum > total) return;

  currentChapter = chapterNum;

  setStep5ChapterHeader();
  showStep4Container();
  setStepStatus("step-4", `Loading (Ch ${currentChapter})...`);

  syncChapterUI();
  await loadChapterState(currentChapter, { open: true });
}

/* ========= Step 1 ========= */
async function refineIdea() {
  const genre = $("#genre").value.trim();
  const idea = $("#idea").value.trim();

  $("#confirm-idea-area").style.display = "none";
  selectedData = null;

  show("#loader-1", true);
  $("#variations-grid").innerHTML = "";
  setDisabled("#btn-refine", true);

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
    show("#loader-1", false);
    setDisabled("#btn-refine", false);
  }
}

function renderVariations(options) {
  const grid = $("#variations-grid");
  grid.innerHTML = "";

  options.forEach((opt) => {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `<h3>${opt.title}</h3><div class="desc">${opt.description}</div>`;

    card.addEventListener("click", () => {
      $$(".card").forEach((c) => c.classList.remove("selected"));
      card.classList.add("selected");
      selectedData = opt;
      $("#confirm-idea-area").style.display = "block";
      setStepStatus("step-1", "Selected");
      openStep("step-1");
      updatePlanButtonUI();
    });

    grid.appendChild(card);
  });
}

/* ========= Step 2 ========= */
async function generatePlot() {
  if (!selectedData) return;

  await ensureProject();

  openStep("step-2");
  setStepStatus("step-2", "Running...");
  show("#loader-2", true);
  show("#plot-content", false);
  setDisabled("#btn-generate-chars", true);

  try {
    const plotData = await fetchJSON(api("/plot"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(selectedData),
    });

    currentPlotData = plotData;
    renderPlot(plotData);

    currentChapter = 1;
    syncChapterUI();

    setStepStatus("step-2", "Done");
    setDisabled("#btn-generate-chars", false);
  } catch (e) {
    console.error(e);
    alert("Error generating plot");
    setStepStatus("step-2", "Error");
  } finally {
    show("#loader-2", false);
  }
}

function renderPlot(data) {
  const container = $("#plot-content");
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

/* ========= Step 3 ========= */
async function generateCharacters() {
  if (!currentPlotData || !selectedData) return;

  await ensureProject();

  openStep("step-3");
  setStepStatus("step-3", "Running...");
  show("#loader-3", true);
  show("#chars-container", false);

  const summary = (currentPlotData.chapters || []).map((c) => `Ch${c.number}: ${c.summary}`).join("\n");

  try {
    const data = await fetchJSON(api("/characters"), {
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
    show("#loader-3", false);
  }
}

function renderCharacters(data) {
  show("#chars-container", true);

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

  $("#protagonists-grid").innerHTML = (data.protagonists || []).map(createCard).join("");
  $("#antagonists-grid").innerHTML = (data.antagonists || []).map(createCard).join("");
  $("#supporting-grid").innerHTML = (data.supporting || []).map(createCard).join("");
}

function wireCharacterDeleteDelegation() {
  const container = $("#chars-container");
  if (!container) return;

  container.addEventListener("click", async (event) => {
    const btn = event.target.closest("button[data-char-id]");
    if (!btn) return;

    const id = btn.getAttribute("data-char-id");
    if (!id) return;

    try {
      await ensureProject();

      btn.disabled = true;
      await fetchJSON(api(`/characters/${id}`), { method: "DELETE" });

      const st = await fetchJSON(api(`/state?chapter=${currentChapter}`));
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

/* ========= Step 4 ========= */
async function planCurrentChapter() {
  if (!currentPlotData?.chapters?.length || !selectedData) return;

  await ensureProject();

  const ch = currentPlotData.chapters[currentChapter - 1];
  if (!ch) return;

  openStep("step-4", { scroll: false });
  setStepStatus("step-4", `Running (Ch ${currentChapter})...`);
  show("#loader-4", true);
  show("#beats-container", false);

  setStep5Enabled(false);
  enableWriteIt(false);
  setChapterTitleDisplay();

  try {
    const data = await fetchJSON(api("/chapter_plan"), {
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

    // wipe prose for this chapter after planning
    try {
      await fetchJSON(api("/beat/clear_from"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chapter: currentChapter, from_beat_index: 0 }),
      });
    } catch (_) {}

    beatTexts = {};

    show("#loader-4", false);
    show("#beats-container", true);

    renderBeats(currentBeats);
    beatAudio = {};
    await refreshAudioStatusForChapter(currentChapter);
    renderWriteBeats(currentBeats, beatTexts);

    setStepStatus("step-4", `Done (Ch ${currentChapter})`);
    setStepStatus("step-5", `Ready`);

    setStep5Enabled(true);
    enableWriteIt(true);
    updatePlanButtonUI();

    openStep("step-5", { scroll: false });
  } catch (e) {
    console.error(e);
    alert("Error planning chapter");
    setStepStatus("step-4", "Error");
  } finally {
    show("#loader-4", false);
    show("#beats-container", true);
    updatePlanButtonUI();
  }
}

function renderBeats(beats) {
  show("#beats-container", true);
  const list = $("#beats-list");
  if (!list) return;

  list.innerHTML = "";
  beats.forEach((beat) => {
    const t = (beat.type || "").toLowerCase();
    let typeClass = "type-description";
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

/* ========= Step 5 ========= */
function renderWriteBeats(beats, textsByIdx) {
  const wrap = $("#write-beats-list");
  if (!wrap) return;

  wrap.innerHTML = "";
  beats.forEach((beat, idx) => {
    const txt = textsByIdx?.[idx] || "";
    const isWritten = txt.trim().length > 0;
    const safeText = highlightDialogueToHtml(txt);

    const active = getActiveTtsProvider();
    const anyAudioExists = TTS_PROVIDERS.some((p) => {
      const st = getBeatAudio(idx, p.key);
      return !!(st.exists && st.url);
    });
    const showAudioBlock = isWritten || anyAudioExists;

    const audioControlsHtml = showAudioBlock
      ? `
        <div class="tts-block" style="margin-top:10px; display:flex; flex-direction:column; gap:8px;">
          ${TTS_PROVIDERS.map((p) => {
            const st = getBeatAudio(idx, p.key);
            const isActive = active === p.key;
            const hasAudio = !!(st.exists && st.url);

            // If we have audio: show audio controls, and show Regenerate only for active provider.
            if (hasAudio) {
              return `
                <div class="tts-row" style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
                  <span style="min-width:72px; font-size:0.85rem; color:#64748b;">${p.label}</span>
                  ${
                    isActive
                      ? `<button data-audio-generate="${idx}" data-tts-provider="${p.key}" style="background:#0ea5e9;">Regenerate</button>`
                      : ``
                  }
                  <audio
                    data-audio-el="${idx}"
                    data-tts-provider="${p.key}"
                    controls
                    controlslist="nodownload"
                    preload="metadata"
                    style="width:320px; height:32px; display:none;"
                  ></audio>
                </div>
              `;
            }

            // If missing/error/generating: show Generate button (disabled if not active) and a status label.
            const disabledAttr = isActive ? "" : "disabled";
            const statusText = st.status || "missing";

            return `
              <div class="tts-row" style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
                <span style="min-width:72px; font-size:0.85rem; color:#64748b;">${p.label}</span>
                <button
                  data-audio-generate="${idx}"
                  data-tts-provider="${p.key}"
                  ${disabledAttr}
                  style="background:#0ea5e9;"
                  title="${isActive ? "" : "This TTS provider is not loaded"}"
                >Generate</button>
                <span
                  data-audio-status="${idx}"
                  data-tts-provider="${p.key}"
                  style="font-size:0.85rem; color:${statusText === "error" ? "#ef4444" : "#64748b"};"
                >${statusText}</span>
              </div>
            `;
          }).join("")}
        </div>
      `
      : "";

    wrap.innerHTML += `
      <div class="beat-item" id="write-beat-row-${idx}">
        <div style="display:flex; flex-direction:column; gap:6px; min-width:180px;">
          <div style="font-weight:700;">Beat ${idx + 1}</div>
          <div style="font-size:0.85rem; color:${isWritten ? "#16a34a" : "#64748b"};">
            ${isWritten ? "Written" : "Not written"}
          </div>
          <button data-write-beat="${idx}" style="background:#6366f1;">${isWritten ? "Rewrite" : "Write"}</button>
          ${isWritten ? `<button data-clear-beat="${idx}" style="background:#ef4444;">Clear</button>` : ""}
          ${isWritten ? `<button data-clear-from="${idx}" style="background:#b91c1c;">Clear from here</button>` : ""}
        </div>

        <div class="beat-desc" style="width:100%;">
          <div style="font-weight:700; margin-bottom:6px;">${beat.type}</div>
          <div style="margin-bottom:10px;">${beat.description}</div>

          <div style="margin-top:10px; border-top:1px solid #e2e8f0; padding-top:10px;">
            <div style="font-weight:700; color:#334155; margin-bottom:6px;">Generated text</div>
            ${
              isWritten
                ? `<pre id="beat-prose-${idx}" style="white-space:pre-wrap; margin:0; padding:10px; background:#0b1220; color:#e2e8f0; border-radius:8px;">${safeText}</pre>`
                : `<div id="beat-prose-${idx}" style="color:#64748b; font-style:italic;">(not written yet)</div>`
            }
            ${audioControlsHtml}
          </div>
        </div>
      </div>
    `;
  });

  beats.forEach((_, idx) => updateBeatAudioRowUI(idx));
}

function wireWriteBeatDelegation() {
  const wrap = $("#write-beats-list");
  if (!wrap) return;

  wrap.addEventListener("click", async (event) => {
    const clearBtn = event.target.closest("button[data-clear-beat]");
    if (clearBtn) return clearBeat(Number(clearBtn.getAttribute("data-clear-beat")));

    const clearFromBtn = event.target.closest("button[data-clear-from]");
    if (clearFromBtn) return clearFrom(Number(clearFromBtn.getAttribute("data-clear-from")));

    const genAudioBtn = event.target.closest("button[data-audio-generate]");
    if (genAudioBtn) {
      const idx = Number(genAudioBtn.getAttribute("data-audio-generate"));
      const provider = (genAudioBtn.getAttribute("data-tts-provider") || "").toLowerCase();
      if (Number.isNaN(idx) || !provider) return;

      setBeatAudioStatus(idx, provider, "generating", { exists: false, url: "" });

      try {
        const force = !!getBeatAudio(idx, provider)?.exists;

        await fetchJSON(api("/audio/generate"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ chapter: currentChapter, beat_index: idx, provider, force }),
        });

        startAudioPoll(currentChapter);
      } catch (e) {
        console.error(e);
        setBeatAudioStatus(idx, provider, "error", { exists: false, url: "" });
      }
      return;
    }

    const writeBtn = event.target.closest("button[data-write-beat]");
    if (!writeBtn) return;

    const idx = Number(writeBtn.getAttribute("data-write-beat"));
    const isRewrite = !!(beatTexts[idx] && beatTexts[idx].trim().length);
    if (isRewrite) await clearFrom(idx + 1);
    await writeBeat(idx);
  });
}

async function clearBeat(idx) {
  if (Number.isNaN(idx)) return;

  await ensureProject();
  await disableWriteControls(true);

  try {
    await fetchJSON(api("/beat/clear"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chapter: currentChapter, beat_index: idx }),
    });

    delete beatTexts[idx];
    renderWriteBeats(currentBeats, beatTexts);
    await refreshAudioStatusForChapter(currentChapter);

    setStepStatus("step-5", `Beat ${idx + 1} cleared`);
  } catch (e) {
    console.error(e);
    alert("Failed to clear beat in DB");
  } finally {
    await disableWriteControls(false);
  }
}

async function clearFrom(fromIdx) {
  if (Number.isNaN(fromIdx)) return;

  await ensureProject();
  await disableWriteControls(true);

  try {
    await fetchJSON(api("/beat/clear_from"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chapter: currentChapter, from_beat_index: fromIdx }),
    });

    Object.keys(beatTexts).forEach((k) => {
      const i = Number(k);
      if (!Number.isNaN(i) && i >= fromIdx) delete beatTexts[i];
    });

    renderWriteBeats(currentBeats, beatTexts);
    await refreshAudioStatusForChapter(currentChapter);

    setStepStatus("step-5", `Cleared from beat ${fromIdx + 1}`);
  } catch (e) {
    console.error(e);
    alert("Failed to clear beats in DB");
  } finally {
    await disableWriteControls(false);
  }
}

async function clearAllBeats() {
  if (!currentBeats?.length) return;
  openStep("step-5", { scroll: false });
  setStepStatus("step-5", "Clearing all...");
  await clearFrom(0);
}

async function generateAllBeats() {
  if (!currentBeats?.length) return;

  openStep("step-5", { scroll: false });

  let start = firstUnwrittenIndex();
  if (start === null) {
    await clearAllBeats();
    start = 0;
  }

  await disableWriteControls(true);
  try {
    for (let i = start; i < currentBeats.length; i++) {
      if (beatTexts[i]?.trim()) continue;

      setStepStatus("step-5", `Generating ${i + 1} / ${currentBeats.length}...`);

      const proseEl = $(`#beat-prose-${i}`);
      if (proseEl) {
        proseEl.textContent = "(writing...)";
        proseEl.style.color = "#64748b";
        proseEl.style.fontStyle = "italic";
      }

      const data = await fetchJSON(api(`/write_beat?chapter=${currentChapter}&beat_index=${i}`));
      beatTexts[i] = data.text || "";
      renderWriteBeats(currentBeats, beatTexts);
    }

    setStepStatus("step-5", "Saving continuity...");
    await buildChapterContinuity(currentChapter);

    setStepStatus("step-5", "Generate all done");
  } catch (e) {
    console.error(e);
    alert("Generate all stopped due to an error");
    setStepStatus("step-5", "Error");
  } finally {
    await disableWriteControls(false);
  }
}

async function writeBeat(beatIndex) {
  if (!currentBeats?.length) return;

  await ensureProject();

  openStep("step-5", { scroll: false });
  setStepStatus("step-5", `Writing beat ${beatIndex + 1}...`);

  await disableWriteControls(true);

  const proseEl = $(`#beat-prose-${beatIndex}`);
  if (proseEl) {
    proseEl.textContent = "(writing...)";
    proseEl.style.color = "#64748b";
    proseEl.style.fontStyle = "italic";
  }

  try {
    const data = await fetchJSON(api(`/write_beat?chapter=${currentChapter}&beat_index=${beatIndex}`));
    beatTexts[beatIndex] = data.text || "";
    renderWriteBeats(currentBeats, beatTexts);

    await refreshAudioStatusForChapter(currentChapter);

    if (beatIndex === currentBeats.length - 1) await buildChapterContinuity(currentChapter);

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
  const idx = firstUnwrittenIndex();
  if (idx === null) return;
  await writeBeat(idx);
}

async function disableWriteControls(disabled) {
  setStep5Enabled(!disabled);
  setChapterNavEnabled(!disabled);
  $$("button[data-write-beat]").forEach((b) => (b.disabled = disabled));
  $$("button[data-clear-beat]").forEach((b) => (b.disabled = disabled));
  $$("button[data-clear-from]").forEach((b) => (b.disabled = disabled));
}

async function buildChapterContinuity(chapterNum) {
  try {
    await ensureProject();
    await fetchJSON(api("/chapter/continuity"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chapter: chapterNum }),
    });
  } catch (e) {
    console.warn("Continuity build failed (non-fatal):", e);
  }
}

function setStep5ChapterHeader() {
  const ch = currentPlotData?.chapters?.[currentChapter - 1];
  const el = $("#step-5-chapter-title");
  if (!el) return;
  el.innerText = ch ? `Ch ${currentChapter}: ${ch.title}` : `Ch ${currentChapter}`;
}
