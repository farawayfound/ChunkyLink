# vpoRAG — Product Overview

## Purpose
vpoRAG converts enterprise documents (PDF, PPTX, DOCX, TXT, CSV) into structured JSONL knowledge bases optimized for Amazon Q Developer's local context feature. It enables RAG-like inference without vector databases by using local PowerShell search scripts to filter relevant chunks before Amazon Q analyzes them.

## Primary Use Case
Internal VPO (Video Product Operations) triage support. Engineers describe issues in Amazon Q, which automatically searches the indexed KB and Jira ticket database to generate hypotheses, diagnostic queries (Splunk SPL, VO Kibana, OpenSearch DQL), and recommended next steps.

## Key Features
- **Multi-format ingestion**: PDF, PPTX, DOCX, TXT, CSV
- **NLP enrichment**: Auto-classification into 7 categories, auto-tagging, entity extraction via spaCy `en_core_web_md`
- **Cross-references**: Bidirectional semantic chunk linking using spaCy word vectors (≥0.65 similarity)
- **Incremental processing**: Hash-based change detection — only new/modified files reprocessed
- **Category routing**: Chunks split into domain-specific JSONL files (troubleshooting, queries, sop, manual, reference, glossary, general)
- **Domain-aware search**: Multi-phase PowerShell search (4–8 phases, 75–920 chunks) with relevance scoring
- **Jira integration**: Direct SQL queries against VIDPROD_MAIN + CSV fallback for DPSTRIAGE and POSTRCA tickets
- **Web UI**: Flask + SocketIO control panel for config editing and index building (port 5000)
- **Deduplication**: Configurable fuzzy deduplication (intensity 0–9) using RapidFuzz
- **Persistent learned KB**: Session-discovered knowledge saved to `chunks.learned.jsonl` via `learn` MCP tool or `learn_local.py` CLI — version-controlled, synced across engineers, searchable in Phase 3.5

## Target Users
VPO triage engineers using Amazon Q Developer in VS Code for real-time troubleshooting assistance.

## Output
Structured JSONL files in `JSON/` consumed by Amazon Q via PowerShell search scripts — never loaded directly via `@folder` (would exceed context limits at 75K+ tokens).

## What This Is NOT
- Not a vector database or embedding system
- Not a real-time or API-based system
- `Setup/Unimplemented/` folder contains placeholder code only — NOT implemented or functional

## Query Systems Supported
Three completely separate diagnostic query systems, each with distinct syntax:
| System | Target | Syntax |
|---|---|---|
| Splunk SPL | Microservice API logs | `index=aws-*` · `\| stats` · `\| rex` |
| VO Kibana | STB/AMS health metrics | Plain text + field filters, no pipes |
| OpenSearch DQL | Quantum client-side events | `field.path: value AND field2: (v1 OR v2)` |
