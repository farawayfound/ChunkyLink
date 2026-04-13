# Tech Context

## Languages and frameworks

- **Python 3:** `backend/`, `worker/`, top-level `indexers/` (tooling), `backend/indexers/` (runtime indexing used by the API).
- **FastAPI:** `backend/main.py` — REST + SSE; serves `frontend/dist/` when present.
- **React + TypeScript + Vite:** `frontend/`.
- **Redis (async):** Redis Streams for **Library** job queue (`backend/library/queue.py`). Backend tolerates Redis being down at startup and retries (`lifespan` in `backend/main.py`).

## AI / NLP

- **Ollama:** Primary chat model; async HTTP client in `backend/chat/ollama_client.py`. Defaults in `backend/config.py` (e.g. `OLLAMA_MODEL`, `OLLAMA_NUM_CTX`). **Admin** and `DATA_DIR/admin_config.json` can override model and prompts at runtime.
- **spaCy (`en_core_web_md`):** Classification, tagging, semantic helpers in indexer code under `backend/indexers/` (and mirrored concepts in top-level `indexers/`).

## Data layout

- **JSONL:** Chunk stores under `DATA_DIR/indexes/` (demo AMA KB, per-user workspace indexes).
- **SQLite:** `DATA_DIR/db/chunkylink.db` — sessions, users, invites, etc.
- **Uploads:** `DATA_DIR/uploads/`.
- **Library artifacts:** `DATA_DIR/library/` (`LIBRARY_ARTIFACTS_DIR`).
- **Logs:** `DATA_DIR/logs/`.
- **Runtime admin JSON:** `DATA_DIR/admin_config.json` (model, prompts, sanitize flags).

## Environment variables (high level)

See `backend/config.py` and `.env.example` for the full set. Commonly referenced groups:

- **Paths / server:** `DATA_DIR`, `HOST`, `PORT`, `SECRET_KEY`, `CORS_ORIGINS`
- **Ollama:** `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_TIMEOUT`, `OLLAMA_NUM_CTX`
- **Optional GitHub login:** `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_ALLOWED_ADMINS`, `FRONTEND_URL`
- **SMTP:** `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_USE_TLS`
- **Library:** `REDIS_URL`, `NANOBOT_API_KEY` (shared secret for worker → backend callbacks)
- **Chat / search:** `RELEVANCE_THRESHOLD`, `CHAT_*`, `CHAT_SEARCH_LEVEL`, `SEARCH_RESULT_CACHE_TTL_SEC`
- **Chunking / NLP / OCR / dedup:** `PARA_*`, `ENABLE_*`, `MIN_SIMILARITY_THRESHOLD`, etc.

## Worker (`worker/`)

- Consumes **Redis Streams** (`library:jobs`, consumer group `workers`) — see `worker/queue_consumer.py` (aligned with `backend/library/queue.py`).
- Calls **Ollama** on the worker machine (`OLLAMA_*` in `worker/config.py`).
- Posts results to the **backend** using **`M1_BASE_URL`** (historical name = backend base URL, e.g. `http://192.168.x.x:8000`) and **`NANOBOT_API_KEY`** matching the server.
- **Docker:** `docker/docker-compose.nanobot.yml` builds the worker image; worker uses `OLLAMA_BASE_URL` pointing at the compose **ollama** service. Set **`REDIS_URL`** in `.env.nanobot` to the Redis instance reachable from the worker (usually on the app host).

## Deployment and SSH (AI reference)

Canonical runbook: **`docs/deployment.md`**.

**SSH from the dev machine (passwordless):**

- **Library Research worker node:** `ssh david@nanobot` — Ryzen/Linux host; runs the **`worker/`** process (and/or Docker worker + Ollama per compose). Docs also use `david@nanobot.local` / `Deploy-Nanobot.ps1`; treat as the same role with different host aliases.
- **Primary app host (FastAPI, SPA `dist/`, typical Redis for Library):** `ssh david@macmini` — macOS **LaunchAgent** `com.chunkylink.backend`, repo commonly `~/chunkylink`.

**Linux full-stack example (docs):** systemd unit **`chunkylink`**, paths like `/srv/chunkylink/repo`, deploy script `scripts/deploy_chunkylink.sh` with optional **`DEPLOY_RESET_HARD=1`**. **Mac mini:** `git pull` does **not** refresh UI — run `npm run build` in `frontend/` (or `scripts/setup_macmini.sh`), then restart the LaunchAgent. **Cloudflare:** bypass cache/buffering for SSE (`/api/chat/*`, especially AMA).

## Legacy / optional: `mcp_server/`

The **`mcp_server/`** tree is a **vpoRAG**-era MCP + Jira/Samba stack (`vporag-*` tokens, `/srv/vpo_rag` paths in README). It is **not** part of the ChunkyPotato quick start in `README.md`. Only use it when explicitly working on that subsystem.

## Indexer code locations

- **`backend/indexers/`:** Used by the running app for document indexing.
- **`indexers/`** (repo root): Standalone indexer package and docs (`indexers/README.md`). Keep paths straight when suggesting edits or imports.
