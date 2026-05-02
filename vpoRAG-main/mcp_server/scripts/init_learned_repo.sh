#!/bin/bash
# -*- coding: utf-8 -*-
# One-time setup: initialise the learned KB git repo in JSON/detail/
# Run as vporag: /srv/vpo_rag/venv/bin/python ... or bash this script directly.
# Usage: bash /srv/vpo_rag/mcp_server/scripts/init_learned_repo.sh

set -e
DETAIL_DIR="/srv/vpo_rag/JSON/detail"
LEARNED_FILE="$DETAIL_DIR/chunks.learned.jsonl"

cd "$DETAIL_DIR"

if [ -d ".git" ]; then
    echo "[init_learned_repo] Git repo already exists in $DETAIL_DIR — skipping init."
else
    git init
    git config user.email "vporag@server"
    git config user.name "vpoRAG"

    # .gitignore: track only the learned file
    cat > .gitignore <<'EOF'
# Track only chunks.learned.jsonl — all other JSONL files are managed by the indexer
chunks.jsonl
chunks.general.jsonl
chunks.glossary.jsonl
chunks.manual.jsonl
chunks.queries.jsonl
chunks.reference.jsonl
chunks.sop.jsonl
chunks.troubleshooting.jsonl
EOF

    touch "$LEARNED_FILE"
    git add chunks.learned.jsonl .gitignore
    git commit -m "init: learned KB"
    echo "[init_learned_repo] Done. Repo initialised at $DETAIL_DIR"
fi

# Optional: add GitLab remote after configuring deploy key
# git remote add origin git@gitlab.com:<group>/<repo>.git
