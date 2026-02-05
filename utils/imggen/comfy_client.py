from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import aiohttp


@dataclass(frozen=True)
class ComfyPromptResponse:
    prompt_id: str
    number: int | None = None  # queue position sometimes


class ComfyClient:
    def __init__(self, api_ip: str, timeout_s: int = 300):
        api_ip = api_ip.strip()
        if not api_ip.startswith("http"):
            api_ip = "http://" + api_ip
        self.base = api_ip.rstrip("/")
        self.timeout = aiohttp.ClientTimeout(total=timeout_s)
        self._session: aiohttp.ClientSession | None = None

    async def ainit(self) -> None:
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=self.timeout)

    async def aclose(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    def _s(self) -> aiohttp.ClientSession:
        if not self._session:
            raise RuntimeError("ComfyClient not initialized")
        return self._session

    async def system_stats(self) -> dict[str, Any]:
        async with self._s().get(f"{self.base}/system_stats") as r:
            r.raise_for_status()
            return await r.json()

    async def prompt(
        self, prompt_graph: dict[str, Any], client_id: str | None = None
    ) -> ComfyPromptResponse:
        payload: dict[str, Any] = {"prompt": prompt_graph}
        if client_id:
            payload["client_id"] = client_id
        async with self._s().post(f"{self.base}/prompt", json=payload) as r:
            r.raise_for_status()
            data = await r.json()
        return ComfyPromptResponse(
            prompt_id=data["prompt_id"], number=data.get("number")
        )

    async def history(self, prompt_id: str) -> dict[str, Any]:
        async with self._s().get(f"{self.base}/history/{prompt_id}") as r:
            r.raise_for_status()
            return await r.json()

    async def view(
        self, filename: str, subfolder: str = "", type_: str = "output"
    ) -> bytes:
        params = {"filename": filename, "subfolder": subfolder, "type": type_}
        async with self._s().get(f"{self.base}/view", params=params) as r:
            r.raise_for_status()
            return await r.read()

    async def interrupt(self) -> None:
        async with self._s().post(f"{self.base}/interrupt") as r:
            r.raise_for_status()

    async def free(
        self, unload_models: bool = True, free_memory: bool = True
    ) -> dict[str, Any]:
        # comfy /free exists and is meant for unloading/freeing memory [page:1]
        payload = {"unload_models": unload_models, "free_memory": free_memory}
        async with self._s().post(f"{self.base}/free", json=payload) as r:
            r.raise_for_status()
            return await r.json()

    async def wait_done(
        self, prompt_id: str, poll_ms: int = 500, timeout_s: int = 600
    ) -> dict[str, Any]:
        t0 = asyncio.get_event_loop().time()
        while True:
            h = await self.history(prompt_id)
            # history endpoint returns dict keyed by prompt_id when present
            item = h.get(prompt_id)
            if item and item.get("outputs"):
                return item
            if (asyncio.get_event_loop().time() - t0) > timeout_s:
                raise TimeoutError(f"Comfy prompt timeout: {prompt_id}")
            await asyncio.sleep(poll_ms / 1000.0)

    async def object_info(self) -> dict:
        async with self._s().get(f"{self.base}/object_info") as r:
            r.raise_for_status()
            return await r.json()

    async def models(self, folder: str) -> dict:
        async with self._s().get(f"{self.base}/models/{folder}") as r:
            r.raise_for_status()
            return await r.json()

    async def queue(self) -> dict:
        async with self._s().get(f"{self.base}/queue") as r:
            r.raise_for_status()
            return await r.json()

    async def queue_clear(self) -> dict:
        # clears queue (all). Comfy supports POST /queue [page:2]
        async with self._s().post(f"{self.base}/queue", json={"clear": True}) as r:
            r.raise_for_status()
            return await r.json()

    async def upload_image(
        self,
        data: bytes,
        filename: str,
        subfolder: str = "",
        overwrite: bool = True,
    ) -> dict[str, Any]:
        """
        Uploads image into ComfyUI input/. Returns comfy JSON (contains 'name' typically).
        Route: POST /upload/image (multipart/form-data) [page:6]
        """
        form = aiohttp.FormData()
        form.add_field(
            "image",
            data,
            filename=filename,
            content_type="application/octet-stream",
        )
        form.add_field("subfolder", subfolder)
        form.add_field("overwrite", "1" if overwrite else "0")

        async with self._s().post(f"{self.base}/upload/image", data=form) as r:
            r.raise_for_status()
            return await r.json()
