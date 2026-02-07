# utils/imggen/imggen_provider_comfy.py
from __future__ import annotations

import random
import uuid
from typing import Any

from utils.core_logger import log
from utils.imggen.comfy_client import ComfyClient
from utils.imggen.pipelines import (
    CharacterFromStyleParams,
    Flux2KleinT2IDistilledGGUFParams,
    Flux2KleinT2IDistilledParams,
    Flux2KleinT2IParams,
    build_flux2_klein_character_style_ref_gguf,
    build_flux2_klein_scene_dual_ref_gguf,
    build_flux2_klein_t2i,
    build_flux2_klein_t2i_distilled,
    build_flux2_klein_t2i_distilled_gguf,
    load_template,
)
from utils.prompts import DEFAULT_STYLE_PROMPT
from utils.pydantic_models import SceneFromStyleAndCharParams


class ComfyImgGenProvider:
    def __init__(self, cfg):
        self.cfg = cfg
        self.client = ComfyClient(cfg.COMFY_API_IP, timeout_s=cfg.COMFY_API_TIMEOUT_S)
        self._templates: dict[str, dict[str, Any]] = {}

    async def ainit(self) -> None:
        await self.client.ainit()

    async def ping(self) -> dict:
        return await self.client.system_stats()

    async def free(self) -> dict:
        return await self.client.free(unload_models=True, free_memory=True)

    def _tpl(self, key: str) -> dict[str, Any]:
        if key not in self._templates:
            self._templates[key] = load_template(self.cfg.COMFY_TEMPLATES_DIR, key)
        return self._templates[key]

    async def run_flux2_klein_t2i(self, params: Flux2KleinT2IParams) -> dict[str, Any]:
        tpl = self._tpl("flux2_klein_t2i")
        graph = build_flux2_klein_t2i(tpl, params)

        client_id = str(uuid.uuid4())
        resp = await self.client.prompt(graph, client_id=client_id)
        log.info("Comfy submit prompt_id=%s queue=%s", resp.prompt_id, resp.number)

        item = await self.client.wait_done(
            resp.prompt_id,
            poll_ms=self.cfg.COMFY_OUTPUT_POLL_MS,
            timeout_s=self.cfg.COMFY_API_TIMEOUT_S,
        )
        return {
            "prompt_id": resp.prompt_id,
            "queue_number": resp.number,
            "history_item": item,
        }

    async def run_flux2_klein_t2i_distilled(
        self, params: Flux2KleinT2IDistilledParams
    ) -> dict[str, Any]:
        tpl = self._tpl("flux2_klein_t2i_distilled")
        graph = build_flux2_klein_t2i_distilled(tpl, params)

        client_id = str(uuid.uuid4())
        resp = await self.client.prompt(graph, client_id=client_id)
        log.info(
            "Comfy submit distilled prompt_id=%s queue=%s", resp.prompt_id, resp.number
        )

        item = await self.client.wait_done(
            resp.prompt_id,
            poll_ms=self.cfg.COMFY_OUTPUT_POLL_MS,
            timeout_s=self.cfg.COMFY_API_TIMEOUT_S,
        )
        return {
            "prompt_id": resp.prompt_id,
            "queue_number": resp.number,
            "history_item": item,
        }

    async def run_flux2_klein_t2i_distilled_gguf(
        self, params: Flux2KleinT2IDistilledGGUFParams
    ) -> dict[str, Any]:
        tpl = self._tpl("flux2_klein_t2i_distilled_gguf")
        graph = build_flux2_klein_t2i_distilled_gguf(tpl, params)

        client_id = str(uuid.uuid4())
        resp = await self.client.prompt(graph, client_id=client_id)
        log.info("Comfy submit gguf prompt_id=%s queue=%s", resp.prompt_id, resp.number)

        item = await self.client.wait_done(
            resp.prompt_id,
            poll_ms=self.cfg.COMFY_OUTPUT_POLL_MS,
            timeout_s=self.cfg.COMFY_API_TIMEOUT_S,
        )
        return {
            "prompt_id": resp.prompt_id,
            "queue_number": resp.number,
            "history_item": item,
        }

    async def run_style_gguf(self, prompt: str | None) -> dict:
        text = (prompt or "").strip() or DEFAULT_STYLE_PROMPT
        params = Flux2KleinT2IDistilledGGUFParams(
            prompt=text,
            width=1344,
            height=768,
            steps=4,
            cfg=1.0,
            seed=random.randint(1, 2**31 - 1),
            filename_prefix="STYLE-REF",
        )
        return await self.run_flux2_klein_t2i_distilled_gguf(params)

    async def run_character_from_style_gguf(
        self, params: CharacterFromStyleParams
    ) -> dict:
        tpl = self._tpl("flux2_klein_character_style_ref_gguf")
        params = CharacterFromStyleParams(
            **{**params.__dict__, "seed": random.randint(1, 2**31 - 1)}
        )
        graph = build_flux2_klein_character_style_ref_gguf(tpl, params)

        client_id = str(uuid.uuid4())
        resp = await self.client.prompt(graph, client_id=client_id)
        item = await self.client.wait_done(
            resp.prompt_id,
            poll_ms=self.cfg.COMFY_OUTPUT_POLL_MS,
            timeout_s=self.cfg.COMFY_API_TIMEOUT_S,
        )
        return {
            "prompt_id": resp.prompt_id,
            "queue_number": resp.number,
            "history_item": item,
            "seed": params.seed,
        }

    async def run_scene_dual_ref_gguf(
        self, params: SceneFromStyleAndCharParams
    ) -> dict:
        # Переконайся, що файл flux2_klein_scene_dual_ref_gguf.json існує в папці templates!
        tpl = self._tpl("flux2_klein_scene_dual_ref_gguf")

        # Генеруємо сід, якщо 0
        params = SceneFromStyleAndCharParams(
            **{**params.__dict__, "seed": params.seed or random.randint(1, 2**31 - 1)}
        )

        graph = build_flux2_klein_scene_dual_ref_gguf(tpl, params)

        client_id = str(uuid.uuid4())
        resp = await self.client.prompt(graph, client_id=client_id)

        log.info(
            "Comfy submit scene_dual_ref prompt_id=%s queue=%s",
            resp.prompt_id,
            resp.number,
        )

        item = await self.client.wait_done(
            resp.prompt_id,
            poll_ms=self.cfg.COMFY_OUTPUT_POLL_MS,
            timeout_s=self.cfg.COMFY_API_TIMEOUT_S,
        )
        return {
            "prompt_id": resp.prompt_id,
            "queue_number": resp.number,
            "history_item": item,
            "seed": params.seed,
        }
