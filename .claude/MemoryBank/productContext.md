# Product Context

## Why this exists

Small teams and self-hosters want **document Q&A** and **curated web research** without sending data to third-party LLM APIs. ChunkyPotato keeps **indexes and uploads on disk** you control, uses **Ollama** on your network, and adds **NLP structure** (tags, categories, cross-references) so answers stay tied to real chunks.

## Problems solved

- **Fragmented documents:** Workspace turns uploads into searchable JSONL chunks with optional PII-aware indexing.
- **AMA vs private docs:** AMA uses only the **demo KB**; Workspace uses **per-user** indexes — they are intentionally separate.
- **Research without blind trust:** Library runs a **worker pipeline**, then requires **human review** before import into Workspace.
- **Lightweight access control:** **Invite codes** (no mandatory registration); **Admin** for codes, health, demo index builds, and runtime config.

## User experience (routes)

From `frontend/src/App.tsx`:

| Path | Purpose |
|------|---------|
| `/` | Ask Me Anything (demo KB) |
| `/workspace` | Authenticated — uploads, index, chat |
| `/library` | Authenticated — research jobs, review, import |
| `/admin` | Authenticated admin |
| `/about` | Product info |
| `/resume` | Resume page |
| `/login` | Invite / GitHub login |
| `/documents` | Redirects to `/workspace` |

## Session and privacy behavior

- By default, **Workspace data** is cleared on **logout** or after **inactivity** (backend session cleanup in `backend/main.py`).
- Users may **opt in** to preserve data for the next session from **Workspace settings** (`should_preserve_user_data` / storage helpers).
- **Library** and **index builds** can send **optional completion email** when SMTP is configured.

## Who it is for

Home lab or small-office **self-hosting** on modest hardware (“potato cosplaying as a server”). Production split is often **Mac mini** for the app and **nanobot** for the Library worker — see `techContext.md`.
