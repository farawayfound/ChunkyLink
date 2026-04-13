# -*- coding: utf-8 -*-
"""Nanobot worker entry point — consumer loop that processes research jobs."""
from __future__ import annotations

import asyncio
import logging
import signal
import sys

import httpx

import config
from queue_consumer import QueueConsumer

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("worker")

_shutdown = asyncio.Event()


def _handle_signal(*_):
    log.info("shutdown signal received")
    _shutdown.set()


async def _process_job(consumer: QueueConsumer, stream_id: str, job) -> None:
    """Run the full research pipeline for a single job."""
    from synthesizer.pipeline import JobCancelledError, run_pipeline

    job_id = job.job_id
    log.info("processing job %s — %r", job_id, job.prompt[:80])

    async def cancel_check() -> bool:
        return await consumer.is_cancel_requested(job_id)

    try:
        if await cancel_check():
            log.info("job %s skipped — cancel flag set before pipeline", job_id)
            await consumer.publish_status(
                job_id, "cancelled", "Cancelled by user", progress=0.0, sources_found=0,
            )
            await consumer.ack(stream_id)
            return

        result = await run_pipeline(
            job=job,
            status_cb=lambda status, msg, progress=0.0, sources=0: (
                consumer.publish_status(job_id, status, msg, progress, sources)
            ),
            cancel_check=cancel_check,
        )

        if await cancel_check():
            log.info("job %s stopped after pipeline — cancel flag (race)", job_id)
            await consumer.publish_status(
                job_id, "cancelled", "Cancelled by user", progress=0.0, sources_found=0,
            )
            await consumer.ack(stream_id)
            return

        await _deliver_result(job_id, result)
        await consumer.publish_status(
            job_id, "review", "Research complete — awaiting review",
            progress=1.0, sources_found=len(result.get("sources", [])),
        )
        await consumer.ack(stream_id)
        log.info("job %s complete — %d sources", job_id, len(result.get("sources", [])))

    except JobCancelledError:
        log.info("job %s stopped (cooperative cancel)", job_id)
        await consumer.publish_status(
            job_id, "cancelled", "Cancelled by user", progress=0.0, sources_found=0,
        )
        await consumer.ack(stream_id)

    except Exception as exc:
        log.exception("job %s failed: %s", job_id, exc)
        await consumer.publish_status(job_id, "failed", str(exc))
        await consumer.ack(stream_id)


async def _deliver_result(job_id: str, result: dict) -> None:
    """POST the completed artifact back to the M1 backend."""
    url = f"{config.M1_BASE_URL}/api/library/ingest"
    payload = {
        "job_id": job_id,
        "markdown": result["markdown"],
        "sources": result.get("sources", []),
        "summary": result.get("summary", ""),
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            url,
            json=payload,
            headers={"X-Nanobot-Key": config.NANOBOT_API_KEY},
        )
        resp.raise_for_status()
        log.info("delivered result for %s — %s", job_id, resp.json())


async def main() -> None:
    consumer = QueueConsumer(config.REDIS_URL, config.WORKER_ID)
    await consumer.connect()
    log.info("worker %s listening for jobs...", config.WORKER_ID)

    try:
        while not _shutdown.is_set():
            pair = await consumer.dequeue(timeout_ms=3000)
            if pair is None:
                continue
            stream_id, job = pair
            await _process_job(consumer, stream_id, job)
    except asyncio.CancelledError:
        pass
    finally:
        await consumer.close()
        log.info("worker shut down cleanly")


if __name__ == "__main__":
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _handle_signal)
    asyncio.run(main())
