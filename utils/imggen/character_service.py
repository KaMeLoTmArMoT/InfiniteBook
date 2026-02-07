# utils/imggen/character_service.py
from __future__ import annotations

import asyncio
from pathlib import Path

import anyio
from fastapi import HTTPException, Request, UploadFile

from utils.core_logger import log
from utils.imggen.job_utils import _kv_style_image_key, _now_ts, _save_png_for_project
from utils.imggen.pipelines import CharacterFromStyleParams
from utils.prompts import PROMPT_CHARACTER_ANCHORS_BATCH
from utils.pydantic_models import (
    CharacterImageAnchorsBatch,
    CharacterIn,
    CharactersAnchorsRequest,
)
from utils.utils import call_llm_json, require_project

# --- Key Generators ---


def _kv_chars_anchors_key() -> str:
    return "img:chars:anchors"


def _kv_char_job_key(char_id: int) -> str:
    return f"img:char:{char_id}:job"


def _kv_char_result_key(char_id: int) -> str:
    return f"img:char:{char_id}:result"


def _kv_cover_result_key() -> str:
    return "img:cover:result"


# --- Helpers ---


async def _read_style_image_name(ps) -> str:
    """Returns comfy input filename string (e.g. 'foo.png') or ''."""
    obj = await ps.a_kv_get(_kv_style_image_key())
    if isinstance(obj, dict):
        obj = (
            obj.get("comfy_name")
            or obj.get("comfyname")
            or obj.get("name")
            or obj.get("filename")
        )
    return (obj or "").strip()


async def _ensure_style_image(ps, img_mgr) -> str:
    """
    Ensure project has a style image set in KV.
    If missing but cover exists, upload cover to Comfy input and store name.
    """
    cur = await _read_style_image_name(ps)
    if cur:
        return cur

    cover_res = await ps.a_kv_get(_kv_cover_result_key()) or {}
    saved_path = (cover_res.get("saved_path") or "").strip()
    if not saved_path:
        raise RuntimeError(
            "Missing style image and cover not generated (generate cover or upload style image)"
        )

    p = Path(saved_path)
    if not p.exists():
        raise RuntimeError(f"Cover file missing on disk: {saved_path}")

    data = await anyio.to_thread.run_sync(p.read_bytes)

    res = await img_mgr.provider.client.upload_image(
        data=data,
        filename=p.name,
        subfolder="",
        overwrite=True,
    )
    comfy_name = (res.get("name") or res.get("filename") or "").strip()
    if not comfy_name:
        raise RuntimeError(f"unexpected comfy upload response: {res}")

    await ps.a_kv_set(_kv_style_image_key(), comfy_name)
    return comfy_name


# --- Main Service Functions ---


async def service_generate_anchors(
    store, model, project_id: str, req: CharactersAnchorsRequest
) -> dict:
    ps = await require_project(store, project_id)

    if not req.characters:
        raise HTTPException(status_code=400, detail="No characters provided")

    characters_block = "\n".join(
        f"- (id={c.id}) {c.name}: {c.description}".strip() for c in req.characters
    )

    prompt = PROMPT_CHARACTER_ANCHORS_BATCH.format(
        title=req.title,
        genre=req.genre,
        setting=req.setting or "(not specified)",
        n=len(req.characters),
        characters_block=characters_block,
    )

    batch: CharacterImageAnchorsBatch = await call_llm_json(
        model, prompt, CharacterImageAnchorsBatch, temperature=0.35
    )

    in_ids = [c.id for c in req.characters]
    out_ids = [x.char_id for x in batch.items]
    if len(out_ids) != len(in_ids) or set(out_ids) != set(in_ids):
        raise HTTPException(
            status_code=502, detail="LLM returned mismatching char_id set"
        )

    payload = batch.model_dump()
    await ps.a_kv_set(_kv_chars_anchors_key(), payload)
    return payload


async def service_upload_style_image(
    store, img_mgr, project_id: str, file: UploadFile
) -> dict:
    ps = await require_project(store, project_id)

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")

    res = await img_mgr.provider.client.upload_image(
        data=data,
        filename=file.filename or "style.png",
        subfolder="",
        overwrite=True,
    )

    comfy_name = (res.get("name") or res.get("filename") or "").strip()
    if not comfy_name:
        raise HTTPException(
            status_code=502, detail=f"unexpected comfy upload response: {res}"
        )

    await ps.a_kv_set(_kv_style_image_key(), comfy_name)
    return {"ok": True, "style_image": comfy_name}


async def service_get_image_status(store, project_id: str, char_id: int) -> dict:
    ps = await require_project(store, project_id)
    return await ps.a_kv_get(_kv_char_job_key(char_id)) or {"status": "IDLE"}


async def service_get_image_result(store, project_id: str, char_id: int) -> dict:
    ps = await require_project(store, project_id)
    obj = await ps.a_kv_get(_kv_char_result_key(char_id)) or {}
    if obj.get("saved_path"):
        obj["image_url"] = f"/api/projects/{project_id}/characters/{char_id}/image"
    return obj


async def service_get_image_path(store, project_id: str, char_id: int) -> Path:
    ps = await require_project(store, project_id)
    res = await ps.a_kv_get(_kv_char_result_key(char_id)) or {}
    saved_path = res.get("saved_path")
    if not saved_path:
        raise HTTPException(status_code=404, detail="image not generated")
    p = Path(saved_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="image file missing")
    return p


async def generate_character_image_task(
    *, request, project_id: str, char_id: int, img_mgr
) -> None:
    store = request.app.state.store
    ps = await require_project(store, project_id)

    await ps.a_kv_set(
        _kv_char_job_key(char_id),
        {"status": "RUNNING", "started_at": _now_ts(), "error": None},
    )

    try:
        anchors = await ps.a_kv_get(_kv_chars_anchors_key()) or {}
        style_anchor = anchors.get("style_anchor") or ""
        scene_block = anchors.get("scene_block") or ""

        item = next(
            (
                x
                for x in anchors.get("items", [])
                if int(x.get("char_id")) == int(char_id)
            ),
            None,
        )
        if not item:
            raise RuntimeError(f"No anchors for char_id={char_id}")

        character_anchor = item.get("character_anchor") or ""

        # Auto-fix: if no style image in KV but cover exists -> upload cover
        style_image = await _ensure_style_image(ps, img_mgr)

        params = CharacterFromStyleParams(
            style_anchor=style_anchor,
            scene_block=scene_block,
            character_anchor=character_anchor,
            style_image=style_image,
            width=768,
            height=1152,
            steps=4,
            cfg=1.0,
            seed=0,  # TODO: check
            filename_prefix=f"PRJ-{project_id}-CHAR-{char_id}",
        )

        res = await img_mgr.provider.run_character_from_style_gguf(params)

        itemh = res["history_item"]
        outputs = itemh.get("outputs") or {}
        img_meta = None
        for _, out in outputs.items():
            images = out.get("images") or []
            if images:
                img_meta = images[0]
                break
        if not img_meta:
            raise RuntimeError("No images in comfy outputs")

        png = await img_mgr.provider.client.view(
            filename=img_meta["filename"],
            subfolder=img_meta.get("subfolder", ""),
            type_=img_meta.get("type", "output"),
        )

        saved_path = await _save_png_for_project(
            ps, project_id, png, kind=f"char_{char_id}"
        )

        result = {
            "status": "DONE",
            "finished_at": _now_ts(),
            "saved_path": saved_path,
            "seed": res.get("seed"),
            "comfy": {
                "filename": img_meta.get("filename"),
                "subfolder": img_meta.get("subfolder"),
                "type": img_meta.get("type"),
            },
        }
        await ps.a_kv_set(_kv_char_result_key(char_id), result)
        await ps.a_kv_set(
            _kv_char_job_key(char_id),
            {"status": "DONE", "finished_at": _now_ts(), "error": None},
        )

    except Exception as e:
        await ps.a_kv_set(
            _kv_char_job_key(char_id),
            {"status": "ERROR", "finished_at": _now_ts(), "error": str(e)},
        )
        raise


async def service_run_character_generation_pipeline(
    request: Request,
    project_id: str,
    title: str,
    genre: str,
    setting: str,
    db_chars: dict,
    img_mgr,
) -> int:
    store = request.app.state.store
    model = request.app.state.model
    ps = await require_project(store, project_id)

    char_inputs: list[CharacterIn] = []

    for kind in ("protagonists", "antagonists", "supporting"):
        items = db_chars.get(kind) or []
        for c in items:
            c_id = c.get("id")
            if c_id is not None:
                char_inputs.append(
                    CharacterIn(
                        id=int(c_id),
                        name=c.get("name", "Unknown"),
                        description=c.get("description") or c.get("summary", "") or "",
                    )
                )

    if not char_inputs:
        log.warning(f"Project {project_id}: No characters found to generate visuals.")
        return 0

    log.info(f"Pipeline: Generating anchors for {len(char_inputs)} characters.")

    anchors_req = CharactersAnchorsRequest(
        title=title, genre=genre, setting=setting, characters=char_inputs
    )

    await service_generate_anchors(store, model, project_id, anchors_req)

    log.info("Pipeline: Triggering background image tasks.")
    tasks_started = 0

    for c_in in char_inputs:
        char_id = c_in.id

        job_key = _kv_char_job_key(char_id)
        job = await ps.a_kv_get(job_key) or {}

        if job.get("status") == "RUNNING":
            continue

        task = asyncio.create_task(
            generate_character_image_task(
                request=request,
                project_id=project_id,
                char_id=char_id,
                img_mgr=img_mgr,
            )
        )
        task.set_name(f"charimg:{project_id}:{char_id}")
        tasks_started += 1

    return tasks_started
