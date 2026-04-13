# ChunkyPotato

Self-hostable document RAG system with local LLM inference. No vector database — uses chunk-based search with NLP classification and semantic cross-references.

## Features

- **Ask Me Anything** — RAG-powered Q&A grounded in indexed documents
- **Workspace** — Upload, index, explore, and chat with your own documents (PDF, DOCX, PPTX, TXT, CSV)
- **Library Research** — Queue web research tasks, review synthesized reports, and import approved artifacts into Workspace
- **Local Inference** — Ollama integration with configurable models
- **Invite System** — Share access via invite codes, no registration required
- **Admin Dashboard** — Manage invite codes, monitor activity, system health
- **Notifications & Privacy Controls** — Optional email notifications for long-running jobs; local-first storage with session-preserve controls

## Architecture

- **Backend**: FastAPI + SQLite + JSONL knowledge base
- **Frontend**: React + TypeScript (Vite)
- **LLM**: Ollama (any compatible model)
- **NLP**: spaCy for classification, tagging, and semantic linking
- **Worker pipeline**: Background research/index jobs with review-before-import workflow

## Quick Start

```bash
# Clone and configure
cp .env.example .env
# Edit .env with your settings

# Backend
pip install -r requirements.txt
python -m spacy download en_core_web_md
uvicorn backend.main:app --reload

# Frontend
cd frontend && npm install && npm run dev

# Or use Docker
cd docker && docker compose up
```

On Windows PowerShell, copy the env template with:

```powershell
Copy-Item .env.example .env
```

## Runtime behavior

- By default, uploaded Workspace data is cleared on logout or after inactivity.
- Users can opt in to preserve data for the next session from Workspace settings.
- Library and index builds can optionally send completion emails when configured.

## Deployment

For production/server deployment details and helper scripts, see [`docs/deployment.md`](docs/deployment.md).

## Target Hardware

Designed for modest self-hosting: a small Linux machine at home is enough. This demo runs on decidedly humble hardware with **Ollama**—think “potato cosplaying as a server,” not a rack of accelerators.
