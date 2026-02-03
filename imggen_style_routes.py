from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, Field

from utils.config import CFG
from utils.imggen.imggen_provider_comfy import ComfyImgGenProvider


router = APIRouter(prefix="/api/imggen_style", tags=["imggen_style"])
prov = ComfyImgGenProvider(CFG)


class StyleReq(BaseModel):
    prompt: str | None = Field(default="", description="If empty -> default cyberpunk noir Berlin prompt.")


@router.on_event("startup")
async def _startup():
    await prov.ainit()


@router.post("/create", response_class=Response)
async def create_style(body: StyleReq):
    res = await prov.run_style_gguf(body.prompt)

    item = res["history_item"]
    outputs = item.get("outputs") or {}

    # take first image from first output node
    for _, out in outputs.items():
        images = out.get("images") or []
        if images:
            img = images[0]
            b = await prov.client.view(
                filename=img["filename"],
                subfolder=img.get("subfolder", ""),
                type_=img.get("type", "output"),
            )
            return Response(content=b, media_type="image/png")

    # if no images produced, return debug payload (still 200, but you can change to 500)
    return Response(content=b"", media_type="application/octet-stream")
