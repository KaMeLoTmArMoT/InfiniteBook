from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx
from google import genai
from ollama import AsyncClient
from pydantic import BaseModel, ValidationError

from utils.core_logger import log
from utils.core_models import CFG
from utils.utils import _json_hint, clean_json_response


@dataclass
class GenerateResult:
    raw_text: str
    meta: dict[str, Any]


class OllamaModel:
    """
    Local ollama via /api/chat (matches your current `ollama_client.chat` behavior).
    Assumes you already have an async client object with `.chat(...)`.
    """

    def __init__(self, *, client, model_name: str):
        self.client = client
        self.model_name = model_name

    async def generate_json(
        self,
        prompt: str,
        schema: dict,
        *,
        temperature: float,
        options: dict | None = None,
        tag: str = "ollama",
    ) -> GenerateResult:
        opts = {"temperature": temperature}
        if options:
            opts.update(options)

        resp = await self.client.chat(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            options=opts,
            format=schema,
        )

        raw = resp["message"]["content"]
        meta = {
            "provider": "ollama",
            "model": self.model_name,
            "options": opts,
            # common metrics if present
            "prompt_eval_count": resp.get("prompt_eval_count"),
            "eval_count": resp.get("eval_count"),
            "eval_duration": resp.get("eval_duration"),
            "prompt_eval_duration": resp.get("prompt_eval_duration"),
            "total_duration": resp.get("total_duration"),
            "load_duration": resp.get("load_duration"),
            "done_reason": resp.get("done_reason"),
        }

        log.info(
            "[ollama] %s prompt_eval_count=%s eval_count=%s done_reason=%s",
            tag,
            meta["prompt_eval_count"],
            meta["eval_count"],
            meta["done_reason"],
        )

        return GenerateResult(raw_text=raw, meta=meta)


class OpenRouterModel:
    """
    OpenRouter is OpenAI-compatible. Uses /chat/completions.
    Authentication is Bearer token.
    """

    def __init__(
        self, *, api_base: str, api_key: str, model_name: str, timeout_sec: float = 60.0
    ):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.model_name = model_name
        self.timeout_sec = timeout_sec
        self._client = httpx.AsyncClient(timeout=timeout_sec)

    async def close(self) -> None:
        await self._client.aclose()

    async def check_key_limits(self) -> dict[str, Any] | None:
        # OpenRouter documents GET /api/v1/key to check limit/usage.
        url = f"{self.api_base}/api/v1/key"
        try:
            r = await self._client.get(
                url, headers={"Authorization": f"Bearer {self.api_key}"}
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            log.warning("OpenRouter key check failed: %s", e)
            return None

    async def generate_json(
        self,
        prompt: str,
        schema: dict,
        *,
        temperature: float,
        options: dict | None = None,
        tag: str = "openrouter",
    ) -> GenerateResult:
        max_tokens = options.get("max_tokens") if options else None

        url = f"{self.api_base}/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",  # Bearer auth
            "Content-Type": "application/json",
            # Optional attribution headers (safe to include)
            "HTTP-Referer": "http://localhost",
            "X-Title": "Infinite Book Architect",
        }

        payload: dict[str, Any] = {
            "models": [CFG.OPENROUTER_PRIMARY_MODEL, CFG.OPENROUTER_FALLBACK_MODEL],
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        }
        if isinstance(max_tokens, int):
            payload["max_tokens"] = max_tokens

        try:
            r = await self._client.post(url, headers=headers, json=payload)
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            # Log OpenRouter’s actual error JSON/text for debugging
            body = e.response.text
            log.error(
                "OpenRouter 4xx/5xx: status=%s body=%s",
                e.response.status_code,
                body[:2000],
            )
            raise

        data = r.json()
        raw = data["choices"][0]["message"]["content"]

        log.info(f"Actual used model: {data.get('model', 'unknown')}")

        meta = {
            "provider": "openrouter",
            "model": self.model_name,  # TODO: check if OR returns actual model name used
            "options": {"temperature": temperature, **(options or {})},
            "usage": data.get("usage", {}),
            "id": data.get("id"),
        }
        return GenerateResult(raw_text=raw, meta=meta)


class GoogleGenAIModel:
    def __init__(
        self, *, api_key: str, model_name: str, enable_structured: bool = False
    ):
        self.model_name = model_name
        self.enable_structured = enable_structured
        self.client = genai.Client(api_key=api_key)

    async def generate_json(
        self,
        prompt: str,
        schema: dict,
        *,
        temperature: float,
        options: dict | None = None,
        tag: str = "google",
    ) -> GenerateResult:
        # Gemma-3-27b-it: JSON mode is not enabled -> must use prompt-based JSON.
        p = prompt + _json_hint(schema)

        cfg: dict[str, Any] = {"temperature": temperature}
        if options:
            for k in ("max_output_tokens", "top_p", "top_k", "candidate_count"):
                if k in options:
                    cfg[k] = options[k]

        # Only enable structured mode if explicitly turned on (useful for Gemini models).
        if self.enable_structured:
            cfg["response_mime_type"] = "application/json"
            cfg["response_json_schema"] = schema

        try:
            resp = self.client.models.generate_content(
                model=self.model_name,
                contents=p,
                config=cfg,
            )
        except Exception as e:
            # If structured mode is enabled but not supported, retry once without it.
            msg = str(e)
            if self.enable_structured and "JSON mode is not enabled" in msg:
                log.warning(
                    "[google] %s json mode unsupported for %s -> retrying without schema",
                    tag,
                    self.model_name,
                )
                cfg.pop("response_mime_type", None)
                cfg.pop("response_json_schema", None)
                resp = self.client.models.generate_content(
                    model=self.model_name,
                    contents=p,
                    config=cfg,
                )
            else:
                raise

        raw = (resp.text or "").strip()
        meta = {
            "provider": "google",
            "model": self.model_name,
            "options": {"temperature": temperature, **(options or {})},
            "structured_enabled": self.enable_structured,
        }
        return GenerateResult(raw_text=raw, meta=meta)


class ModelGateway:
    """
    High-level API: hide providers behind `generate_model(...)`.
    No abstract classes, just a small dispatcher.
    """

    def __init__(self, provider: str, impl):
        self.provider = provider
        self.impl = impl

    async def startup(self) -> None:
        log.info(f"Starting up ModelGateway for provider: {self.provider}")
        if self.provider == "openrouter":
            info = await self.impl.check_key_limits()
            if info:
                # shape documented: data.limit_remaining, usage_daily, etc.
                log.info("OpenRouter key info: %s", json.dumps(info)[:2000])

    async def shutdown(self) -> None:
        log.info(f"Shutting down ModelGateway for provider: {self.provider}")
        if hasattr(self.impl, "close"):
            await self.impl.close()

    async def generate_json_validated(
        self,
        prompt: str,
        response_model: type[BaseModel],
        *,
        temperature: float,
        max_retries: int,
        options: dict | None = None,
        tag: str = "llm",
    ) -> BaseModel:
        schema = response_model.model_json_schema()
        last_error: Exception | None = None
        last_raw: str | None = None

        for attempt in range(max_retries + 1):
            p = prompt
            if attempt > 0:
                p = p + _json_hint(schema)
                if last_raw:
                    p = p + "\nINVALID PREVIOUS OUTPUT:\n" + last_raw

            res = await self.impl.generate_json(
                p,
                schema,
                temperature=temperature,
                options=options,
                tag=f"{tag}_attempt_{attempt}",
            )

            raw = res.raw_text
            last_raw = raw

            log.debug("LLM RAW (%s, attempt=%s): %s", self.provider, attempt, raw)

            try:
                return response_model.model_validate_json(raw)
            except Exception as e:
                last_error = e

            data = clean_json_response(raw)
            if data is None:
                last_error = ValueError("Failed to parse JSON from model output")
                continue

            try:
                return response_model.model_validate(data)
            except ValidationError as e:
                last_error = e
                continue

        raise RuntimeError(f"LLM JSON validation failed after retries: {last_error}")


def build_model_gateway():
    if CFG.LLM_PROVIDER == "openrouter":
        log.info("Using OpenRouter model")
        impl = OpenRouterModel(
            api_base=CFG.OPENROUTER_API,
            api_key=CFG.OPENROUTER_API_KEY,
            model_name=CFG.OPENROUTER_PRIMARY_MODEL,
        )
        return ModelGateway("openrouter", impl)

    if CFG.LLM_PROVIDER == "google":
        log.info("Using Google GenAI model")
        impl = GoogleGenAIModel(
            api_key=CFG.GOOGLE_GENAI_API_KEY,
            model_name=CFG.GOOGLE_GENAI_MODEL,
        )
        return ModelGateway("google", impl)

    log.info("Using Ollama default model")
    ollama_client = AsyncClient()
    impl = OllamaModel(client=ollama_client, model_name=CFG.MODEL_NAME)
    return ModelGateway("ollama", impl)
