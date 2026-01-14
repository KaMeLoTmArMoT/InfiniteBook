async function fetchJSON(url, options = {}) {
  const res = await fetch(url, options);
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status} ${res.statusText}: ${txt}`);
  }
  return await res.json();
}

function openStep(stepId, { scroll = true } = {}) {
  const el = document.getElementById(stepId);
  if (!el) return;
  el.open = true;
  if (scroll) el.scrollIntoView({ behavior: "smooth", block: "start" });
}

function setStepStatus(stepId, text) {
  const el = document.getElementById(`${stepId}-status`);
  if (el) el.innerText = text;
}

function enableSingleOpenAccordion() {
  const steps = Array.from(document.querySelectorAll("details.step"));
  steps.forEach((d) => {
    d.addEventListener("toggle", () => {
      if (!d.open) return;
      steps.forEach((other) => {
        if (other !== d) other.open = false;
      });
    });
  });
}

function escapeHTML(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
