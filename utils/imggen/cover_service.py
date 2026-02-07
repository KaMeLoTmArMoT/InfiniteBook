# utils/imggen/cover_service.py


from fastapi import Request

from utils.config import CFG
from utils.imggen.job_utils import _now_ts, _save_png_for_project
from utils.imggen.pipelines import Flux2KleinT2IDistilledGGUFParams
from utils.prompts import PROMPT_FLUX_COVER
from utils.pydantic_models import FluxCoverPrompt
from utils.utils import require_project


def _kv_job_key(kind: str = "cover") -> str:
    return f"img:{kind}:job"


def _kv_prompt_key(kind: str = "cover") -> str:
    return f"img:{kind}:prompt"


def _kv_result_key(kind: str = "cover") -> str:
    return f"img:{kind}:result"


def _join_cover_prompt(anchors: dict) -> str:
    style = (anchors.get("STYLE_ANCHOR") or "").strip()
    scene = (anchors.get("SCENE_BLOCK") or "").strip()
    parts = [p for p in (style, scene) if p]
    return "\n\n".join(parts).strip()


async def _generate_cover_image_task(
    request: Request, project_id: str, img_mgr
) -> None:
    store = request.app.state.store
    model = request.app.state.model
    ps = await require_project(store, project_id)

    await ps.a_kv_set(
        _kv_job_key("cover"),
        {"status": "RUNNING", "started_at": _now_ts(), "error": None},
    )

    try:
        selected = await ps.a_kv_get("selected") or {}
        title = (selected.get("title") or "").strip() or "Untitled"
        genre = (selected.get("genre") or "").strip()
        description = (selected.get("description") or "").strip()

        # 1) LLM -> anchors
        p = PROMPT_FLUX_COVER.format(title=title, genre=genre, description=description)
        anchors: FluxCoverPrompt = await model.generate_json_validated(
            p,
            FluxCoverPrompt,
            temperature=0.4,
            max_retries=CFG.LLM_MAX_RETRIES,
            options=None,
            tag="cover_prompt",
        )
        anchors_payload = anchors.model_dump()
        await ps.a_kv_set(_kv_prompt_key("cover"), anchors_payload)

        # 2) Flux2 Klein T2I (distilled gguf)
        prompt = _join_cover_prompt(anchors_payload)
        if not prompt:
            raise RuntimeError("Empty cover prompt")

        params = Flux2KleinT2IDistilledGGUFParams(
            prompt=prompt,
            width=1344,
            height=768,
            steps=4,
            cfg=1.0,
            seed=0,
            filename_prefix=f"PRJ-{project_id}-COVER",
        )
        res = await img_mgr.provider.run_flux2_klein_t2i_distilled_gguf(params)

        item = res["history_item"]
        outputs = item.get("outputs") or {}
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

        saved_path = await _save_png_for_project(ps, project_id, png, kind="cover")

        result = {
            "status": "DONE",
            "finished_at": _now_ts(),
            "saved_path": saved_path,
            "prompt": prompt,
            "comfy": {
                "filename": img_meta.get("filename"),
                "subfolder": img_meta.get("subfolder"),
                "type": img_meta.get("type"),
            },
        }
        await ps.a_kv_set(_kv_result_key("cover"), result)
        await ps.a_kv_set(
            _kv_job_key("cover"),
            {"status": "DONE", "finished_at": _now_ts(), "error": None},
        )

    except Exception as e:
        await ps.a_kv_set(
            _kv_job_key("cover"),
            {"status": "ERROR", "finished_at": _now_ts(), "error": str(e)},
        )
        raise
