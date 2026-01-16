import json
import re

import ollama
import pynvml


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


def log_ollama_usage(log, tag: str, resp: dict) -> None:
    p = resp.get("prompt_eval_count")
    r = resp.get("eval_count")

    if p is None and r is None:
        return

    log.info(f"[ollama] {tag} prompt_eval_count={p} eval_count={r}")

def _tail_chars(text: str, approx_tokens: int = 400) -> str:
    # Simple heuristic: ~4 chars per token for English-ish text
    n = approx_tokens * 4
    return text[-n:] if text else ""

def _fmt_prev_beats(beats: list[dict], beat_index: int, lookback: int = 4) -> str:
    start = max(0, beat_index - lookback)
    lines = []
    for i in range(start, beat_index):
        b = beats[i]
        lines.append(f"- Beat {i + 1} ({b.get('type','')}): {b.get('description','')}")
    return "\n".join(lines) if lines else "- (none)"


async def _build_write_context(store, chapter: int, beat_index: int, beats: list[dict]) -> dict:
    prev_beats = _fmt_prev_beats(beats, beat_index, lookback=4)

    prev_text = ""
    if beat_index > 0:
        p = await store.a_kv_get(f"ch{chapter}_beat_{beat_index - 1}")
        if p and isinstance(p.get("text"), str):
            prev_text = _tail_chars(p["text"], approx_tokens=400)

    # If we have same-chapter prev_text OR we are chapter 1 => no fallback.
    if chapter <= 1 or prev_text.strip():
        return {
            "prev_text": prev_text,
            "prev_beats": prev_beats,
            "prev_chapter_note": "",
            "prev_chapter_capsule": "",
            "prev_chapter_ending": "",
        }

    # Fallback for Chapter 2+ Beat 1 (or if previous beat text missing):
    prev_ch = chapter - 1

    cap = await store.a_kv_get(f"ch{prev_ch}_continuity")
    capsule_txt = ""
    if isinstance(cap, dict) and isinstance(cap.get("bullets"), list):
        capsule_txt = "\n".join(f"- {b.strip()}" for b in cap["bullets"] if isinstance(b, str) and b.strip())
    elif isinstance(cap, str):
        capsule_txt = cap.strip()

    ending_full = await store.a_get_last_written_beat_text(prev_ch)
    ending_tail = _tail_chars(ending_full, approx_tokens=400) if ending_full.strip() else ""

    return {
        "prev_text": "",  # same chapter has none
        "prev_beats": prev_beats,
        "prev_chapter_note": f"NOTE: The following context is from the PREVIOUS CHAPTER (Ch {prev_ch}).",
        "prev_chapter_capsule": capsule_txt or "(none)",
        "prev_chapter_ending": ending_tail or "(none)",
    }
