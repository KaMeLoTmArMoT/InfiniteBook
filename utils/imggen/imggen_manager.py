from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from utils.core_logger import log
from utils.imggen.image_store import save_image_bytes
from utils.imggen.pipelines import Flux2KleinT2IParams, Flux2KleinT2IDistilledParams, Flux2KleinT2IDistilledGGUFParams
from utils.imggen.imggen_provider_comfy import ComfyImgGenProvider


@dataclass
class ImgJob:
    job_id: str
    pipeline: str
    state: str  # queued|running|done|error|canceled
    error: str | None = None

    created_at: float = 0.0
    started_at: float | None = None
    ended_at: float | None = None

    prompt_id: str | None = None
    queue_number: int | None = None

    images: list[dict[str, Any]] | None = None


RunFn = Callable[[], Awaitable[dict[str, Any]]]


class ImgGenManager:
    def __init__(self, cfg):
        self.cfg = cfg
        self.provider = ComfyImgGenProvider(cfg)
        self._sem = asyncio.Semaphore(int(getattr(cfg, "COMFY_MAX_CONCURRENCY", 1)))
        self._jobs: dict[str, ImgJob] = {}
        self._lock = asyncio.Lock()

    async def ainit(self) -> None:
        await self.provider.ainit()

    def get(self, job_id: str) -> ImgJob | None:
        return self._jobs.get(job_id)

    async def ping(self) -> dict:
        return await self.provider.ping()

    async def free(self) -> dict:
        return await self.provider.free()

    async def interrupt(self) -> bool:
        try:
            await self.provider.client.interrupt()
            return True
        except Exception:
            return False

    async def delete_job(self, job_id: str) -> bool:
        from utils.imggen.image_store import delete_job_dir

        async with self._lock:
            j = self._jobs.pop(job_id, None)
        delete_job_dir(job_id)
        return bool(j)

    async def submit_flux2_klein_t2i(self, params: Flux2KleinT2IParams) -> str:
        job_id = uuid.uuid4().hex
        job = ImgJob(job_id=job_id, pipeline="flux2_klein_t2i", state="queued", created_at=time.time())
        async with self._lock:
            self._jobs[job_id] = job

        async def run_fn():
            return await self.provider.run_flux2_klein_t2i(params)

        asyncio.create_task(self._run_job_common(job_id, run_fn))
        return job_id

    async def submit_flux2_klein_t2i_distilled(self, params: Flux2KleinT2IDistilledParams) -> str:
        job_id = uuid.uuid4().hex
        job = ImgJob(job_id=job_id, pipeline="flux2_klein_t2i_distilled", state="queued", created_at=time.time())
        async with self._lock:
            self._jobs[job_id] = job

        async def run_fn():
            return await self.provider.run_flux2_klein_t2i_distilled(params)

        asyncio.create_task(self._run_job_common(job_id, run_fn))
        return job_id

    async def submit_flux2_klein_t2i_distilled_gguf(self, params: Flux2KleinT2IDistilledGGUFParams) -> str:
        job_id = uuid.uuid4().hex
        job = ImgJob(job_id=job_id, pipeline="flux2_klein_t2i_distilled_gguf", state="queued", created_at=time.time())
        async with self._lock:
            self._jobs[job_id] = job

        async def run_fn():
            return await self.provider.run_flux2_klein_t2i_distilled_gguf(params)

        asyncio.create_task(self._run_job_common(job_id, run_fn))
        return job_id

    async def _run_job_common(self, job_id: str, run_fn: RunFn) -> None:
        job = self._jobs[job_id]

        async with self._sem:
            job.state = "running"
            job.started_at = time.time()

            try:
                res = await run_fn()
                job.prompt_id = res.get("prompt_id")
                job.queue_number = res.get("queue_number")

                item = res["history_item"]
                outputs = item.get("outputs") or {}

                saved: list[dict[str, Any]] = []
                idx = 0
                for _, out in outputs.items():
                    for img in (out.get("images") or []):
                        b = await self.provider.client.view(
                            filename=img["filename"],
                            subfolder=img.get("subfolder", ""),
                            type_=img.get("type", "output"),
                        )
                        stored = save_image_bytes(job_id, idx, b, ext="png")
                        saved.append({"index": idx, "url": stored.url, "path": str(stored.path)})
                        idx += 1

                job.images = saved
                job.ended_at = time.time()
                job.state = "done"
                log.info("IMGGEN done job_id=%s pipeline=%s prompt_id=%s images=%s",
                         job_id, job.pipeline, job.prompt_id, len(saved))

            except asyncio.CancelledError:
                job.ended_at = time.time()
                job.state = "canceled"
                raise

            except Exception as e:
                job.ended_at = time.time()
                job.state = "error"
                job.error = repr(e)
                log.exception("IMGGEN error job_id=%s pipeline=%s err=%r", job_id, job.pipeline, e)
