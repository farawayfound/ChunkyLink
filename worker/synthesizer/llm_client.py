# -*- coding: utf-8 -*-
"""Ollama HTTP client for the worker — mirrors the backend's pattern."""
from __future__ import annotations

import logging

import httpx

import config
from agent_debug_log import agent_log

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
    """Call Ollama /api/generate and return the full response text."""
    use_model = model or config.OLLAMA_MODEL
    use_ctx = int(num_ctx) if num_ctx is not None else config.OLLAMA_NUM_CTX
    options: dict = {
        "temperature": temperature,
        "num_ctx": use_ctx,
    }
    if num_predict is not None:
        options["num_predict"] = int(num_predict)
    payload: dict = {
        "model": use_model,
        "prompt": prompt,
        "stream": False,
        # Top-level only — ``think`` inside ``options`` is ignored by Ollama.  Without this,
        # thinking-capable models (e.g. ``gemma4:26b``) may spend the token budget in
        # ``thinking`` and return an empty ``response``, which breaks the Library pipeline.
        "think": False,
        "options": options,
    }
    if system:
        payload["system"] = system

    base = config.OLLAMA_BASE_URL.rstrip("/")
    # #region agent log
    agent_log(
        hypothesis_id="H3",
        location="llm_client.py:generate:pre_http",
        message="ollama_generate_start",
        data={
            "model": use_model,
            "num_ctx": use_ctx,
            "base_host": base.split("://")[-1][:80],
            "prompt_len": len(prompt or ""),
            "has_system": bool(system),
            "timeout_sec": int(config.OLLAMA_TIMEOUT),
        },
    )
    # #endregion
    try:
        async with httpx.AsyncClient(timeout=config.OLLAMA_TIMEOUT) as client:
            resp = await client.post(f"{base}/api/generate", json=payload)
            resp.raise_for_status()
            data = resp.json()
            if data.get("error"):
                raise RuntimeError(str(data["error"]).strip())
    except Exception as exc:
        # #region agent log
        agent_log(
            hypothesis_id="H3",
            location="llm_client.py:generate:error",
            message="ollama_generate_failed",
            data={"model": use_model, "err_type": type(exc).__name__, "err": str(exc)[:500]},
        )
        # #endregion
        raise

    text = data.get("response") or ""
    think_raw = data.get("thinking") or ""
    # #region agent log
    agent_log(
        hypothesis_id="H3",
        location="llm_client.py:generate:success",
        message="ollama_generate_done",
        data={
            "model": use_model,
            "response_len": len(text),
            "thinking_len": len(str(think_raw)),
        },
    )
    # #endregion
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
