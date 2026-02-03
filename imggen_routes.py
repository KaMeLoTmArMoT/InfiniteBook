from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from utils.config import CFG
from utils.imggen.imggen_manager import ImgGenManager
from utils.imggen.pipelines import Flux2KleinT2IParams, Flux2KleinT2IDistilledParams, Flux2KleinT2IDistilledGGUFParams
from utils.imggen.image_store import image_path

router = APIRouter(prefix="/api/imggen", tags=["imggen"])
mgr = ImgGenManager(CFG)


class SubmitFlux2Klein(BaseModel):
    prompt: str = Field(min_length=1)
    negative: str = ""
    width: int = 1024
    height: int = 1024
    steps: int = 20
    cfg: float = 5.0
    seed: int = 0
    filename_prefix: str = "Flux2-Klein"


class SubmitRequest(BaseModel):
    pipeline: str = Field(min_length=1)
    params: dict = Field(default_factory=dict)


@router.on_event("startup")
async def _startup():
    await mgr.ainit()


@router.get("/ping")
async def ping():
    return await mgr.ping()


@router.post("/free")
async def free():
    return await mgr.free()


@router.post("/interrupt")
async def interrupt():
    ok = await mgr.interrupt()
    return {"ok": ok}


@router.post("/submit")
async def submit(req: SubmitRequest):
    p = req.pipeline.strip().lower()

    if p == "flux2_klein_t2i":
        params = Flux2KleinT2IParams(**req.params)
        job_id = await mgr.submit_flux2_klein_t2i(params)
        return {"job_id": job_id}

    if p == "flux2_klein_t2i_distilled":
        params = Flux2KleinT2IDistilledParams(**req.params)
        job_id = await mgr.submit_flux2_klein_t2i_distilled(params)
        return {"job_id": job_id}

    if p == "flux2_klein_t2i_distilled_gguf":
        params = Flux2KleinT2IDistilledGGUFParams(**req.params)
        job_id = await mgr.submit_flux2_klein_t2i_distilled_gguf(params)
        return {"job_id": job_id}

    raise HTTPException(status_code=400, detail=f"unknown pipeline: {p}")


@router.get("/status/{job_id}")
async def status(job_id: str):
    j = mgr.get(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="job not found")
    return {
        "job_id": j.job_id,
        "pipeline": j.pipeline,
        "state": j.state,
        "error": j.error,
        "created_at": j.created_at,
        "started_at": j.started_at,
        "ended_at": j.ended_at,
        "prompt_id": j.prompt_id,
        "queue_number": j.queue_number,
        "images": j.images,
    }


@router.get("/image/{job_id}/{index}")
async def get_image(job_id: str, index: int):
    p = image_path(job_id, int(index), ext="png")
    if not p.exists():
        raise HTTPException(status_code=404, detail="image not found")
    return FileResponse(str(p), media_type="image/png")


@router.delete("/job/{job_id}")
async def delete_job(job_id: str):
    ok = await mgr.delete_job(job_id)
    return {"ok": ok}


@router.post("/queue/clear")
async def queue_clear():
    return await mgr.provider.client.queue_clear()
