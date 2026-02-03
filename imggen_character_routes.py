from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from utils.config import CFG
from utils.imggen.imggen_provider_comfy import ComfyImgGenProvider
from utils.imggen.pipelines import CharacterFromStyleParams


router = APIRouter(prefix="/api/imggen_character", tags=["imggen_character"])
prov = ComfyImgGenProvider(CFG)


class CharacterReq(BaseModel):
    style_anchor: str = Field(default="")
    scene_block: str = Field(default="")
    character_anchor: str = Field(default="")
    style_image: str = Field(default="", description="Filename in Comfy input/. Use /upload first.")
    width: int = 768
    height: int = 1152
    steps: int = 4
    cfg: float = 1.0
    seed: int = 0
    filename_prefix: str = "HERO-BASE"


@router.on_event("startup")
async def _startup():
    await prov.ainit()


@router.post("/create", response_class=Response)
async def create_character(body: CharacterReq):
    params = CharacterFromStyleParams(**body.model_dump())
    if not params.style_image.strip():
        raise HTTPException(status_code=400, detail="style_image is required (upload it to Comfy input/ first)")

    res = await prov.run_character_from_style_gguf(params)

    item = res["history_item"]
    outputs = item.get("outputs") or {}
    for _, out in outputs.items():
        images = out.get("images") or []
        if images:
            img = images[0]
            b = await prov.client.view(
                filename=img["filename"],
                subfolder=img.get("subfolder", ""),
                type_=img.get("type", "output"),
            )
            return Response(content=b, media_type="image/png", headers={"X-Seed": str(res["seed"])})

    raise HTTPException(status_code=500, detail="No images in comfy outputs")
