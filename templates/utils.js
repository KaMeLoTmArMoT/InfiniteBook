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
  return String(s || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function isWordChar(ch){
  return ch != null && /[A-Za-z0-9_]/.test(ch);
}
function isBoundary(ch){
  // boundary = start/end OR not a "word char"
  return ch == null || !isWordChar(ch);
}

function highlightDialogueToHtml(raw){
  raw = String(raw || "");
  let out = "";
  let i = 0;

  while (i < raw.length){
    const ch = raw[i];
    const prev = i > 0 ? raw[i - 1] : null;
    const next = i + 1 < raw.length ? raw[i + 1] : null;

    // Curly quotes: “ ... ”
    if (ch === "“"){
      let j = i + 1;
      while (j < raw.length && raw[j] !== "”") j++;
      if (j < raw.length){
        out += `<span class="dlg">${escapeHTML(raw.slice(i, j + 1))}</span>`;
        i = j + 1;
        continue;
      }
    }

    // Double quotes: " ... "
    if (ch === `"`){
      // optional: require boundary before opening quote (reduces false positives)
      if (isBoundary(prev)){
        let j = i + 1;
        while (j < raw.length){
          if (raw[j] === `"` && raw[j - 1] !== "\\") break;
          j++;
        }
        if (j < raw.length){
          out += `<span class="dlg">${escapeHTML(raw.slice(i, j + 1))}</span>`;
          i = j + 1;
          continue;
        }
      }
    }

    // Single quotes: ' ... ' but NOT apostrophes in words (Kaito's, didn't)
    if (ch === `'`){
      // opening ' must be after a boundary (start/space/punct/newline)
      if (isBoundary(prev)){
        let j = i + 1;
        while (j < raw.length){
          if (raw[j] === `'`){
            const before = raw[j - 1];
            const after = (j + 1 < raw.length) ? raw[j + 1] : null;

            // treat as apostrophe if it's between word chars: didn' t / Kaito's
            const isApostropheInWord = isWordChar(before) && isWordChar(after);

            // closing quote if it's NOT word-internal and next is boundary/end
            const isClosingQuote = !isApostropheInWord && isBoundary(after);

            if (isClosingQuote) break;
          }
          j++;
        }

        if (j < raw.length){
          out += `<span class="dlg">${escapeHTML(raw.slice(i, j + 1))}</span>`;
          i = j + 1;
          continue;
        }
      }
    }

    out += escapeHTML(ch);
    i++;
  }

  return out;
}

