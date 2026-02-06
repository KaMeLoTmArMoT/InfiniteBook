import asyncio
import time
from pathlib import Path

import anyio

from utils.core_logger import log

IMG_DIR = Path("data/images/generated")
IMG_DIR.mkdir(parents=True, exist_ok=True)


def _now_ts() -> int:
    return int(time.time())


def _attach_task_logger(task: asyncio.Task, label: str) -> None:
    def _done(t: asyncio.Task):
        try:
            t.result()
        except Exception as e:
            log.exception("Background task failed (%s): %s", label, e)

    task.add_done_callback(_done)


def _kv_cover_seq_key() -> str:
    return "img:cover:seq"


async def _next_cover_seq(ps) -> int:
    obj = await ps.a_kv_get(_kv_cover_seq_key()) or {}
    cur = int(obj.get("value") or 0)
    nxt = cur + 1
    await ps.a_kv_set(_kv_cover_seq_key(), {"value": nxt})
    return nxt


async def _save_png_for_project(
    store, project_id: str, png_bytes: bytes, kind: str = "cover"
) -> str:
    seq = await _next_cover_seq(store)
    out = IMG_DIR / project_id
    out.mkdir(parents=True, exist_ok=True)
    # fn = f"{kind}_{uuid.uuid4().hex}.png"
    fn = f"{kind}_{seq:04d}.png"
    path = out / fn
    await anyio.to_thread.run_sync(path.write_bytes, png_bytes)
    return str(path)
