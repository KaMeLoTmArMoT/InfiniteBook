# utils/imggen/scene_service.py
from __future__ import annotations

import asyncio
from pathlib import Path

import anyio

from utils.core_logger import log
from utils.imggen.character_service import (
    _ensure_style_image,
    _kv_char_result_key,
    _kv_chars_anchors_key,
)
from utils.imggen.job_utils import (
    _attach_task_logger,
    _kv_style_image_key,
    _now_ts,
    _save_png_for_project,
)
from utils.imggen.pipelines import CharacterFromStyleParams, SceneFromStyleAndCharParams
from utils.prompts import PROMPT_SELECT_SCENES
from utils.pydantic_models import ChapterScenesPlan
from utils.utils import call_llm_json, require_project

# --- Keys ---


def _kv_chapter_scenes_plan_key(chapter_num: int) -> str:
    return f"img:chapter:{chapter_num}:scenes_plan"


def _kv_scene_job_key(chapter_num: int, beat_index: int) -> str:
    return f"img:chapter:{chapter_num}:scene:{beat_index}:job"


def _kv_scene_result_key(chapter_num: int, beat_index: int) -> str:
    return f"img:chapter:{chapter_num}:scene:{beat_index}:result"


# --- Service Logic ---


async def service_plan_chapter_images(
    store, model, project_id: str, chapter_num: int, beats: list[dict]
) -> ChapterScenesPlan:
    anchors_data = await store.a_kv_get(_kv_chars_anchors_key()) or {}
    char_items = anchors_data.get("items", [])

    chars_visual_text = "\n".join(
        f"- ID {x.get('char_id')}: {x.get('name')} - {x.get('character_anchor')}"
        for x in char_items
    )

    beats_text = "\n".join(
        f"[{i}] ({b.get('type')}): {b.get('description')}" for i, b in enumerate(beats)
    )
    log.info(
        f"--- [LLM INPUT] Beats for Ch{chapter_num} ---\n{beats_text[:500]}...\n(Total {len(beats)} beats)"
    )

    total = len(beats)
    q1 = total // 3
    q2 = (total * 2) // 3

    proj = await store.a_get_project(project_id)

    prompt = PROMPT_SELECT_SCENES.format(
        title=proj.get("title", "Story"),
        total_beats=total,
        q1=q1,
        q2=q2,
        characters_visuals=chars_visual_text,
        beats_text=beats_text,
    )

    log.info(f"Planning scenes for Ch {chapter_num} via LLM...")

    scenes_plan = await call_llm_json(model, prompt, ChapterScenesPlan, temperature=0.4)

    log.info(f"--- [LLM OUTPUT] Plan for Ch{chapter_num} ---")
    for s in scenes_plan.scenes:
        log.info(
            f"  Beat {s.beat_index}: CharID={s.primary_character_id} | Prompt='{s.visual_description[:50]}...'"
        )

    return scenes_plan


async def generate_scene_image_task(
    *,
    request,
    project_id: str,
    chapter_num: int,
    beat_index: int,
    visual_prompt: str,
    character_id: int | None,
    img_mgr,
) -> None:
    store = request.app.state.store
    ps = await require_project(store, project_id)

    job_key = _kv_scene_job_key(chapter_num, beat_index)

    await ps.a_kv_set(
        job_key,
        {"status": "RUNNING", "started_at": _now_ts(), "error": None},
    )

    try:
        anchors = await ps.a_kv_get(_kv_chars_anchors_key()) or {}
        style_anchor = anchors.get("style_anchor") or ""

        style_image = await _ensure_style_image(ps, img_mgr)

        use_dual_ref = False
        char_image_filename = ""
        char_anchor_text = ""

        # Спроба знайти картинку персонажа
        if character_id is not None:
            char_res = await ps.a_kv_get(_kv_char_result_key(character_id)) or {}
            saved_path = char_res.get("saved_path")

            if saved_path:
                p = Path(saved_path)
                if p.exists():
                    data = await anyio.to_thread.run_sync(p.read_bytes)
                    res_up = await img_mgr.provider.client.upload_image(
                        data=data,
                        filename=p.name,
                        subfolder="",
                        overwrite=True,
                    )
                    char_image_filename = res_up.get("name") or p.name
                    use_dual_ref = True

            if not use_dual_ref:
                log.warning(
                    f"Ch{chapter_num}:{beat_index} requested CharID={character_id}, but image not found. Fallback to Style-only."
                )

        # --- LOGGING FOR COMFY ---
        log.info(f"--- [COMFY INPUT] Scene Ch{chapter_num}:{beat_index} ---")
        log.info(f"  Type: {'DUAL REF' if use_dual_ref else 'SINGLE REF'}")
        log.info(f"  Style Anchor: {style_anchor[:50]}...")
        log.info(f"  Visual Prompt (Scene): {visual_prompt}")
        log.info(f"  Style Image: {style_image}")
        if use_dual_ref:
            log.info(f"  Char Image: {char_image_filename}")
        # -------------------------

        if use_dual_ref:
            params = SceneFromStyleAndCharParams(
                style_anchor=style_anchor,
                scene_block=visual_prompt,
                character_anchor="",
                style_image=style_image,
                char_image=char_image_filename,
                width=1152,
                height=768,
                steps=4,
                cfg=1.0,
                seed=0,
                filename_prefix=f"PRJ-{project_id}-CH{chapter_num}-BEAT{beat_index}",
            )
            res = await img_mgr.provider.run_scene_dual_ref_gguf(params)
        else:
            params = CharacterFromStyleParams(
                style_anchor=style_anchor,
                scene_block="",
                character_anchor=visual_prompt,
                style_image=style_image,
                width=1152,
                height=768,
                steps=4,
                cfg=1.0,
                seed=0,
                filename_prefix=f"PRJ-{project_id}-CH{chapter_num}-BEAT{beat_index}",
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
            ps, project_id, png, kind=f"ch{chapter_num}_beat{beat_index}"
        )

        result = {
            "status": "DONE",
            "finished_at": _now_ts(),
            "saved_path": saved_path,
            "seed": res.get("seed"),
            "visual_prompt": visual_prompt,
            "used_char_id": character_id if use_dual_ref else None,
        }

        await ps.a_kv_set(_kv_scene_result_key(chapter_num, beat_index), result)
        await ps.a_kv_set(
            job_key,
            {"status": "DONE", "finished_at": _now_ts(), "error": None},
        )

    except Exception as e:
        log.error(f"Scene Ch{chapter_num} Beat{beat_index} FAILED: {e}")
        await ps.a_kv_set(
            job_key,
            {"status": "ERROR", "finished_at": _now_ts(), "error": str(e)},
        )
        raise


async def service_run_scene_generation_pipeline(
    request, project_id: str, chapter_num: int, img_mgr
) -> int:
    store = request.app.state.store
    model = request.app.state.model
    ps = await require_project(store, project_id)

    state = await ps.a_load_state(chapter=chapter_num)
    beats = state.get("beats", {}).get("beats", [])

    if not beats:
        return 0

    # 1. Plan
    plan: ChapterScenesPlan = await service_plan_chapter_images(
        store, model, project_id, chapter_num, beats
    )

    await ps.a_kv_set(_kv_chapter_scenes_plan_key(chapter_num), plan.model_dump())

    # 2. Trigger Tasks
    count = 0
    for scene in plan.scenes:
        task = asyncio.create_task(
            generate_scene_image_task(
                request=request,
                project_id=project_id,
                chapter_num=chapter_num,
                beat_index=scene.beat_index,
                visual_prompt=scene.visual_description,
                character_id=scene.primary_character_id,
                img_mgr=img_mgr,
            )
        )
        _attach_task_logger(
            task, f"scene:{project_id}:{chapter_num}:{scene.beat_index}"
        )
        count += 1

    return count
