# api/routes_imggen.py
from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response

from utils.imggen.image_store import image_path
from utils.imggen.imggen_manager import ImgGenManager
from utils.pydantic_models import *

router = APIRouter(prefix="/api/imggen", tags=["imggen"])

mgr = ImgGenManager(CFG)


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
    # keep in mind: method name depends on your Comfy client implementation
    return await mgr.provider.client.queue_clear()


@router.post("/upload", response_model=UploadResp)
async def upload_image(file: UploadFile = File(...)):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")

    res = await mgr.provider.client.upload_image(
        data=data,
        filename=file.filename or "upload.png",
        subfolder="",
        overwrite=True,
    )

    comfy_name = res.get("name") or res.get("filename")
    if not comfy_name:
        raise HTTPException(
            status_code=502, detail=f"unexpected comfy upload response: {res}"
        )

    return UploadResp(comfy_name=comfy_name, raw=res)


@router.post("/create_style", response_class=Response)
async def create_style(body: StyleReq):
    res = await mgr.provider.run_style_gguf(body.prompt)

    item = res["history_item"]
    outputs = item.get("outputs") or {}
    for _, out in outputs.items():
        images = out.get("images") or []
        if images:
            img = images[0]
            b = await mgr.provider.client.view(
                filename=img["filename"],
                subfolder=img.get("subfolder", ""),
                type_=img.get("type", "output"),
            )
            return Response(content=b, media_type="image/png")

    return Response(content=b"", media_type="application/octet-stream")


@router.post("/create_character", response_class=Response)
async def create_character(body: CharacterReq):
    params = CharacterFromStyleParams(**body.model_dump())
    if not params.style_image.strip():
        raise HTTPException(
            status_code=400,
            detail="style_image is required (upload it to Comfy input/ first)",
        )

    res = await mgr.provider.run_character_from_style_gguf(params)

    item = res["history_item"]
    outputs = item.get("outputs") or {}
    for _, out in outputs.items():
        images = out.get("images") or []
        if images:
            img = images[0]
            b = await mgr.provider.client.view(
                filename=img["filename"],
                subfolder=img.get("subfolder", ""),
                type_=img.get("type", "output"),
            )
            return Response(
                content=b,
                media_type="image/png",
                headers={"X-Seed": str(res.get("seed", 0))},
            )

    raise HTTPException(status_code=500, detail="No images in comfy outputs")
