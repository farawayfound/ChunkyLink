# -*- coding: utf-8 -*-
"""Ollama HTTP client for the worker — mirrors the backend's pattern."""
from __future__ import annotations

import json
import logging

import httpx

import config

log = logging.getLogger(__name__)


def _assistant_from_chat_raw(raw: str) -> tuple[str, str]:
    """Parse ``/api/chat`` response body. Returns (assistant_text, error_or_empty).

    Handles a single JSON object, or NDJSON (concatenate non-empty ``message.content``).
    If ``content`` is empty but ``thinking`` is set on the final object, uses ``thinking``.
    """
    raw = (raw or "").strip()
    if not raw:
        return "", ""
    try:
        d = json.loads(raw)
        if isinstance(d, dict):
            if d.get("error"):
                return "", str(d["error"]).strip()
            m = d.get("message") or {}
            if isinstance(m, dict):
                c = str(m.get("content") or "").strip()
                th = str(m.get("thinking") or "").strip()
                if c:
                    return c, ""
                if th:
                    return th, ""
            return "", ""
    except json.JSONDecodeError:
        pass

    err = ""
    parts: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(d, dict):
            continue
        if d.get("error"):
            err = str(d["error"]).strip()
        m = d.get("message") or {}
        if isinstance(m, dict):
            c = str(m.get("content") or "")
            if c:
                parts.append(c)
    merged = "".join(parts).strip()
    if merged:
        return merged, err
    return "", err


def _assistant_from_generate_dict(data: dict) -> str:
    """Visible text from ``/api/generate`` JSON."""
    if data.get("error"):
        raise RuntimeError(str(data["error"]).strip())
    text = str(data.get("response") or "").strip()
    thinking = str(data.get("thinking") or "").strip()
    if not text and thinking:
        log.warning(
            "ollama generate: empty response, using thinking (%d chars)",
            len(thinking),
        )
        return thinking
    return text


async def generate(
    prompt: str,
    system: str = "",
    temperature: float = 0.3,
    num_predict: int | None = None,
    *,
    model: str | None = None,
    num_ctx: int | None = None,
) -> str:
    """Complete prompt via Ollama.

    Prefer ``POST /api/chat`` with ``stream: false`` and ``think: false`` — this is
    the reliable combination for Gemma 4 / thinking models.  Falls back to
    ``/api/generate`` if chat fails (e.g. older Ollama).
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

    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    base = config.OLLAMA_BASE_URL.rstrip("/")
    read_sec = float(max(int(config.OLLAMA_TIMEOUT), 900))
    timeout = httpx.Timeout(connect=30.0, read=read_sec, write=30.0, pool=30.0)

    chat_payload: dict = {
        "model": use_model,
        "messages": messages,
        "stream": False,
        "think": False,
        "keep_alive": -1,
        "options": options,
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            r = await client.post(f"{base}/api/chat", json=chat_payload)
            r.raise_for_status()
            text, cerr = _assistant_from_chat_raw(r.text)
            if text:
                log.info("ollama chat: %d chars, model=%s", len(text), use_model)
                return text
            if cerr:
                log.warning("ollama chat empty body with error line: %s", cerr[:200])
        except Exception as exc:
            log.warning("ollama chat failed (%s), trying /api/generate", exc)

        gen_payload: dict = {
            "model": use_model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "options": options,
        }
        if system:
            gen_payload["system"] = system
        try:
            r2 = await client.post(f"{base}/api/generate", json=gen_payload)
            r2.raise_for_status()
            data2 = r2.json()
            out = _assistant_from_generate_dict(data2)
            if out:
                log.info("ollama generate: %d chars, model=%s", len(out), use_model)
                return out
        except Exception as exc:
            log.warning("ollama generate with think=false failed: %s", exc)

        # Last resort: generate without ``think`` (pre-26b style).
        gen_payload.pop("think", None)
        r3 = await client.post(f"{base}/api/generate", json=gen_payload)
        r3.raise_for_status()
        out = _assistant_from_generate_dict(r3.json())
        if not out.strip():
            raise RuntimeError(
                "Ollama returned no assistant text after /api/chat, "
                "/api/generate (think=false), and /api/generate (legacy). "
                f"Check model={use_model!r}, num_ctx={use_ctx}, and Ollama logs."
            )
        log.info("ollama generate (no think flag): %d chars, model=%s", len(out), use_model)
        return out


async def quick_generate(
    prompt: str,
    *,
    model: str | None = None,
    num_ctx: int | None = None,
) -> str:
    """Lightweight wrapper for search-query generation."""
    return await generate(prompt, temperature=0.5, model=model, num_ctx=num_ctx)
