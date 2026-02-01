const $ = (sel, root = document) => root.querySelector(sel);

let selectedProject = null;

function setStatus(text) {
  const el = $("#projects-status");
  if (el) el.textContent = text;
}

function setLoading(yes) {
  const loader = $("#projects-loader");
  if (loader) loader.style.display = yes ? "block" : "none";
}

function setSelected(project) {
  selectedProject = project;

  const idEl = $("#current-project-id");
  if (idEl) idEl.textContent = project?.id || "(none)";

  const btn = $("#btn-open-app");
  if (btn) btn.disabled = !project?.id;
}

function projectCardHtml(p) {
  const safeTitle = (p.title || "Untitled").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
  return `
    <div class="card" data-project-id="${p.id}" style="cursor:pointer;">
      <div style="display:flex; justify-content:space-between; gap:10px; align-items:flex-start;">
        <h3 style="margin:0;">${safeTitle}</h3>
        <button class="mini-danger" data-delete-project="${p.id}" style="cursor:pointer;">Delete</button>
      </div>
      <div class="desc" style="opacity:.9; word-break:break-all;">${p.id}</div>
    </div>
  `;
}

async function loadProjects() {
  setLoading(true);
  setStatus("Loading...");

  const grid = $("#projects-grid");
  grid.innerHTML = "";

  try {
    const res = await fetchJSON("/api/projects");
    const items = res?.items || [];

    if (!items.length) {
      grid.innerHTML = `<div class="card"><h3>No projects</h3><div class="desc">Create one above.</div></div>`;
      setStatus("Empty");
      setSelected(null);
      return;
    }

    grid.innerHTML = items.map(projectCardHtml).join("");

    // auto-select from localStorage if present
    const saved = localStorage.getItem("ib_project_id");
    const found = saved ? items.find((x) => x.id === saved) : null;
    setSelected(found || items[0]);

    setStatus("Ready");
  } catch (e) {
    console.error(e);
    setStatus("Error");
    grid.innerHTML = `<div class="card"><h3>Error</h3><div class="desc">Failed to load projects.</div></div>`;
  } finally {
    setLoading(false);
  }
}

async function createProject() {
  const titleEl = $("#new-project-title");
  const langEl = $("#new-project-language");

  const title = titleEl?.value?.trim() || "Untitled";
  const language = (langEl?.value || "en").toLowerCase();

  setStatus("Creating...");
  try {
    const res = await fetchJSON("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, language }),
    });

    const p = res?.project;
    if (!p?.id) throw new Error("Invalid create response");

    if (titleEl) titleEl.value = "";
    localStorage.setItem("ib:project:id", p.id);
    setSelected(p);
    await loadProjects();
    setStatus("Created");
  } catch (e) {
    console.error(e);
    setStatus("Error");
    alert("Failed to create project");
  }
}

async function deleteProject(projectId) {
  if (!confirm("Delete this project? This will remove its DB data. Audio files are not deleted automatically.")) return;

  setStatus("Deleting...");
  try {
    await fetchJSON(`/api/projects/${projectId}`, { method: "DELETE" });

    const saved = localStorage.getItem("ib_project_id");
    if (saved === projectId) localStorage.removeItem("ib_project_id");

    await loadProjects();
    setStatus("Deleted");
  } catch (e) {
    console.error(e);
    setStatus("Error");
    alert("Failed to delete project");
  }
}

function openApp() {
  if (!selectedProject?.id) return;
  localStorage.setItem("ib_project_id", selectedProject.id);
  window.location.href = "/";
}

document.addEventListener("DOMContentLoaded", () => {
  $("#btn-create-project")?.addEventListener("click", createProject);
  $("#btn-refresh-projects")?.addEventListener("click", loadProjects);
  $("#btn-open-app")?.addEventListener("click", openApp);

  $("#projects-grid")?.addEventListener("click", async (ev) => {
    const delBtn = ev.target.closest("button[data-delete-project]");
    if (delBtn) {
      await deleteProject(delBtn.getAttribute("data-delete-project"));
      return;
    }

    const card = ev.target.closest("[data-project-id]");
    if (!card) return;

    const id = card.getAttribute("data-project-id");
    const title = card.querySelector("h3")?.textContent || "Untitled";
    setSelected({ id, title });

    // visually mark selection
    [...document.querySelectorAll("#projects-grid .card")].forEach((c) => c.classList.remove("selected"));
    card.classList.add("selected");
  });

  loadProjects();
});
