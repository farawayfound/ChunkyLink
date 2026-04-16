# -*- coding: utf-8 -*-
"""Ollama HTTP client for the worker — mirrors the backend's pattern."""
from __future__ import annotations

import logging

import httpx

import config

log = logging.getLogger(__name__)


async def generate(
    prompt: str,
    system: str = "",
    temperature: float = 0.3,
    num_predict: int | None = None,
    *,
    model: str | None = None,
    num_ctx: int | None = None,
) -> str:
    """Call Ollama ``/api/generate`` (non-streaming) and return assistant text.

    Uses ``POST /api/generate`` like pre-26b deployments.  For ``gemma4:26b`` and
    other thinking-capable models, ``think: false`` must be a **top-level**
    field (not inside ``options``) or the model may fill ``thinking`` and leave
    ``response`` empty.  If ``response`` is still empty, we fall back to
    ``thinking`` so Library jobs do not fail silently.
    """
    use_model = model or config.OLLAMA_MODEL
    use_ctx = int(num_ctx) if num_ctx is not None else config.OLLAMA_NUM_CTX
    options: dict = {
        "temperature": temperature,
        "num_ctx": use_ctx,
    }
    if num_predict is not None:
        options["num_predict"] = int(num_predict)
    elif len(prompt or "") + len(system or "") > 12000:
        options["num_predict"] = 12288

    payload: dict = {
        "model": use_model,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "options": options,
    }
    if system:
        payload["system"] = system

    base = config.OLLAMA_BASE_URL.rstrip("/")
    read_sec = float(max(int(config.OLLAMA_TIMEOUT), 900))
    timeout = httpx.Timeout(connect=30.0, read=read_sec, write=30.0, pool=30.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(f"{base}/api/generate", json=payload)
        resp.raise_for_status()
        data = resp.json()
        if data.get("error"):
            raise RuntimeError(str(data["error"]).strip())

    text = str(data.get("response") or "").strip()
    thinking = str(data.get("thinking") or "").strip()
    if not text and thinking:
        log.warning(
            "ollama generate: empty response field, using thinking (%d chars), model=%s",
            len(thinking),
            use_model,
        )
        text = thinking

    log.info("ollama generate: %d chars, model=%s", len(text), use_model)
    return text


async def quick_generate(
    prompt: str,
    *,
    model: str | None = None,
    num_ctx: int | None = None,
) -> str:
    """Lightweight wrapper for search-query generation."""
    return await generate(prompt, temperature=0.5, model=model, num_ctx=num_ctx)
