from __future__ import annotations

import uuid
from typing import Any

from utils.core_logger import log
from utils.imggen.comfy_client import ComfyClient
from utils.imggen.pipelines import (
    load_template,
    Flux2KleinT2IParams,
    build_flux2_klein_t2i, Flux2KleinT2IDistilledParams, build_flux2_klein_t2i_distilled,
    build_flux2_klein_t2i_distilled_gguf, Flux2KleinT2IDistilledGGUFParams,
)


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
        return {"prompt_id": resp.prompt_id, "queue_number": resp.number, "history_item": item}

    async def run_flux2_klein_t2i_distilled(self, params: Flux2KleinT2IDistilledParams) -> dict[str, Any]:
        tpl = self._tpl("flux2_klein_t2i_distilled")
        graph = build_flux2_klein_t2i_distilled(tpl, params)

        client_id = str(uuid.uuid4())
        resp = await self.client.prompt(graph, client_id=client_id)
        log.info("Comfy submit distilled prompt_id=%s queue=%s", resp.prompt_id, resp.number)

        item = await self.client.wait_done(
            resp.prompt_id,
            poll_ms=self.cfg.COMFY_OUTPUT_POLL_MS,
            timeout_s=self.cfg.COMFY_API_TIMEOUT_S,
        )
        return {"prompt_id": resp.prompt_id, "queue_number": resp.number, "history_item": item}

    async def run_flux2_klein_t2i_distilled_gguf(self, params: Flux2KleinT2IDistilledGGUFParams) -> dict[str, Any]:
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
        return {"prompt_id": resp.prompt_id, "queue_number": resp.number, "history_item": item}
