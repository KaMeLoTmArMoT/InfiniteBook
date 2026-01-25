# tts/utils.py
import asyncio
import hashlib
import json

import ollama
import psutil
import pynvml


# --- JSON HELPERS (fallback) ---
def clean_json_response(raw: str) -> dict | list | None:
    """
    Placeholder. Import your real implementation.
    """
    raw = raw.strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        # extremely minimal fallback; keep your existing robust one
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start: end + 1])
            except Exception:
                return None
    return None


def _json_hint(schema: dict) -> str:
    return (
        "\nIMPORTANT: Return ONLY valid JSON matching this schema. "
        "No markdown. No prose. No extra keys.\n"
        f"SCHEMA:\n{json.dumps(schema)}\n"
    )


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
        models = await asyncio.wait_for(asyncio.to_thread(ollama.list), timeout=1.0)
        return {"status": "online", "model_count": len(models.get("models", []))}
    except:
        return {"status": "offline", "model_count": 0}


def log_ollama_usage(log, tag: str, resp: dict) -> None:
    p = resp.get("prompt_eval_count", "- No data -")
    r = resp.get("eval_count", "- No data -")
    done_reason = resp.get("done_reason", "- No data -")

    log.info(f"[ollama] {tag} prompt_eval_count={p} eval_count={r} done_reason={done_reason}")


def get_ram_status():
    vm = psutil.virtual_memory()
    return {"used": int(vm.used), "total": int(vm.total)}


def _tail_chars(text: str, approx_tokens: int = 400) -> str:
    # Simple heuristic: ~4 chars per token for English-ish text
    n = approx_tokens * 4
    return text[-n:] if text else ""


def _fmt_prev_beats(beats: list[dict], beat_index: int, lookback: int = 4) -> str:
    start = max(0, beat_index - lookback)
    lines = []
    for i in range(start, beat_index):
        b = beats[i]
        lines.append(f"- Beat {i + 1} ({b.get('type', '')}): {b.get('description', '')}")
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


def _stable_seed(*parts) -> int:
    s = "|".join(str(p) for p in parts)
    h = hashlib.blake2b(s.encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(h, "big")


def pick_num_predict(beat_type: str) -> int:
    t = (beat_type or "").lower()
    base = 220
    if "action" in t:
        base = 180
    if "dialogue" in t:
        base = 260
    if "internal" in t or "monologue" in t:
        base = 240

    # deterministic “jitter” (reproducible per beat if you pass seed)
    return max(120, min(420, base))


def beat_generation_options(*, beat_type: str, chapter: int, beat_index: int) -> dict:
    # deterministic seed so reruns keep similar length/feel
    seed = _stable_seed("write_beat", chapter, beat_index, beat_type)

    # small jitter derived from seed (no random module needed)
    jitter = (seed % 141) - 60  # [-60..80]
    num_predict = max(120, min(420, pick_num_predict(beat_type) + jitter))

    # “human-ish” but still controlled
    return {
        # "num_predict": num_predict,  # TODO: also tmp disable as breaks json
        "top_p": 0.9,
        "top_k": 30,
        "typical_p": 0.7,
        "repeat_penalty": 1.12,
        "presence_penalty": 0.3,
        "frequency_penalty": 0.2,
        # "seed": seed,  # TODO: do not use for now
    }

async def get_cpu_status_async():
    cpu = await asyncio.to_thread(psutil.cpu_percent, 0.2)
    return {"cpu_load": cpu}
