# Project Brief

> **Memory bank:** This folder is `.claude/MemoryBank/` (PascalCase). “Memory bank” in instructions refers to these files.

**Name:** ChunkyPotato (workspace / clone often named **ChunkyLink**).

**Description:** Self-hostable document RAG with local LLM inference. There is **no vector database** — retrieval uses **chunk-based search**, NLP classification, and semantic cross-references over **JSONL** indexes under `DATA_DIR`.

## Naming: product vs infrastructure

The UI product name is **ChunkyPotato**. Paths, systemd, service user, SQLite file, session cookie, and `CHUNKYLINK_*` deploy variables use **`chunkylink`** so existing servers stay compatible. See `docs/deployment.md`.

## Core objectives

- Ground **Ask Me Anything** (AMA) in a **demo** index under `DATA_DIR/indexes/demo`.
- Let authenticated users **upload, index, explore, and chat** with their own documents in **Workspace** (PDF, DOCX, PPTX, TXT, CSV).
- Run **Library Research**: queue web research jobs, stream status, **review** synthesized reports, approve/reject, and **import** approved artifacts into Workspace.
- Keep inference **local-first** via **Ollama**; optional **SMTP** for invites and long-running job email.

## Non-goals (default mental model)

Do **not** assume the legacy **vpoRAG** stack (MCP server, Jira/Samba/MySQL under `mcp_server/`) unless the task explicitly touches that directory. ChunkyPotato’s primary app is `backend/` + `frontend/` + `worker/`.

## Key surfaces

- **API:** FastAPI in `backend/main.py` — routers under `/api/auth`, `/api/chat`, `/api/documents`, `/api/index`, `/api/admin`, `/api/library`.
- **Auth:** SQLite (`DATA_DIR/db/chunkylink.db`) — invites; optional **GitHub OAuth** via env (`GITHUB_*`).
- **Library worker:** Redis Streams + optional `worker/` process on a separate host (often **nanobot**).
