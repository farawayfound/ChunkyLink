# -*- coding: utf-8 -*-
"""Full research pipeline: search -> scrape -> synthesize."""
from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable, Coroutine, Optional

import config
from crawler.search import run_search
from crawler.scraper import scrape_urls
from synthesizer.llm_client import generate, quick_generate
from synthesizer.prompts import (
    build_synthesis_prompt,
    current_date_context,
    system_for_format,
)

log = logging.getLogger(__name__)

StatusCallback = Callable[..., Coroutine[Any, Any, None]]
CancelCheck = Optional[Callable[[], Awaitable[bool]]]


class JobCancelledError(Exception):
    """Raised when the API sets a cooperative-cancel flag (Redis) mid-run."""


async def run_pipeline(
    job,
    status_cb: StatusCallback | None = None,
    cancel_check: CancelCheck = None,
) -> dict:
    """Execute the full research pipeline and return the artifact.

    Returns dict with keys: markdown, sources, summary.

    Model/context config is read from ``config.OLLAMA_MODEL`` /
    ``config.OLLAMA_NUM_CTX`` (default 24k / 24576; override via ``OLLAMA_NUM_CTX`` in ``.env.nanobot``).
    """

    async def _status(status: str, msg: str, progress: float = 0.0, sources: int = 0):
        if status_cb:
            await status_cb(status, msg, progress, sources)

    async def _abort_if_cancelled() -> None:
        if cancel_check is None:
            return
        try:
            if await cancel_check():
                raise JobCancelledError()
        except JobCancelledError:
            raise
        except Exception as exc:
            log.debug("cancel_check failed (ignored): %s", exc)

    llm_model = config.OLLAMA_MODEL
    llm_num_ctx = config.OLLAMA_NUM_CTX

    async def _llm_quick(prompt: str) -> str:
        return await quick_generate(prompt, model=llm_model, num_ctx=llm_num_ctx)

    # -- Phase 1: Search ---------------------------------------------------
    await _abort_if_cancelled()
    await _status("crawling", "Searching the web...", 0.1)

    date_context = current_date_context()

    search_results = await run_search(
        prompt=job.prompt,
        max_results=job.max_sources,
        llm_fn=_llm_quick,
        date_context=date_context,
    )

    await _abort_if_cancelled()

    if not search_results:
        raise RuntimeError("No search results found for the given prompt.")

    urls = [r.url for r in search_results]
    await _status("crawling", f"Found {len(urls)} URLs — scraping pages...", 0.3, len(urls))

    # -- Phase 2: Scrape ---------------------------------------------------
    pages = await scrape_urls(
        urls,
        max_concurrent=config.MAX_CONCURRENT_SCRAPES,
        timeout=config.SCRAPE_TIMEOUT,
    )

    await _abort_if_cancelled()

    good_pages = [p for p in pages if p.success and len(p.content) > 100]
    if not good_pages:
        raise RuntimeError("All page scrapes failed or returned empty content.")

    await _status(
        "synthesizing",
        f"Scraped {len(good_pages)}/{len(pages)} pages — synthesizing report...",
        0.6, len(good_pages),
    )

    # -- Phase 3: Synthesize -----------------------------------------------
    sources_for_llm = []
    for i, page in enumerate(good_pages):
        sr = next((r for r in search_results if r.url == page.url), None)
        sources_for_llm.append({
            "url": page.url,
            "title": page.title or (sr.title if sr else f"Source {i+1}"),
            "content": page.content,
        })

    await _abort_if_cancelled()

    output_format = getattr(job, "output_format", "default") or "default"
    synthesis_num_predict = 1800 + (job.max_sources * 500)
    user_prompt = build_synthesis_prompt(
        job.prompt, sources_for_llm, output_format=output_format,
        num_predict=synthesis_num_predict,
    )

    log.info(
        "synthesis starting: %d sources, prompt=%d chars, num_predict=%d, model=%s",
        len(sources_for_llm), len(user_prompt), synthesis_num_predict, llm_model,
    )
    t_synth = time.perf_counter()
    await _status("synthesizing", "Synthesizing report...", 0.75, len(sources_for_llm))
    markdown = await generate(
        user_prompt,
        system=system_for_format(output_format, date_context=date_context),
        temperature=0.3,
        num_predict=synthesis_num_predict,
        model=llm_model,
        num_ctx=llm_num_ctx,
    )
    synth_elapsed = time.perf_counter() - t_synth
    log.info(
        "synthesis complete in %.1fs: %d chars output",
        synth_elapsed, len(markdown),
    )

    await _abort_if_cancelled()

    if not markdown or len(markdown.strip()) < 100:
        raise RuntimeError("LLM synthesis returned empty or too-short output.")

    await _status("synthesizing", "Generating summary...", 0.9, len(good_pages))

    await _abort_if_cancelled()
    t_sum = time.perf_counter()
    summary = await generate(
        f"Summarize in 2-3 sentences:\n\n{markdown[:3000]}",
        temperature=0.2,
        num_predict=512,
        model=llm_model,
        num_ctx=4096,
    )
    log.info("summary generated in %.1fs", time.perf_counter() - t_sum)

    source_list = [
        {"url": s["url"], "title": s["title"]}
        for s in sources_for_llm
    ]

    log.info(
        "pipeline complete: %d chars markdown, %d sources",
        len(markdown), len(source_list),
    )

    return {
        "markdown": markdown,
        "sources": source_list,
        "summary": summary.strip(),
    }
