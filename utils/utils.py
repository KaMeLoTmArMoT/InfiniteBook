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
