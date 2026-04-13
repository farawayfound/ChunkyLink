# Active Context

## Baseline

Memory bank **regenerated and aligned with the ChunkyPotato repo on 2026-04-13**. Before stating deploy steps, hostnames, or env defaults, **re-verify** `README.md` and `docs/deployment.md` — those are the source of truth for production layout (Mac mini LaunchAgent vs Linux `chunkylink` systemd, `DEPLOY_RESET_HARD`, frontend `dist/` rebuild, Cloudflare SSE).

## Default agent assumptions

- Product is **ChunkyPotato**; infra naming **chunkylink** where paths and services matter.
- **Library** requires **Redis** and a running **`worker/`** consumer on the worker host; **AMA** requires only the **demo** index and Ollama.
- **Learn / dedup** for library import paths: **`backend/learn/learn_engine.py`**, not `mcp_server/`.

## Current focus (placeholder)

No single active sprint is encoded here. When you start a focused effort (e.g. Library UX, indexer performance, deploy automation), replace this section with **one or two concrete bullets** so agents prioritize correctly.
