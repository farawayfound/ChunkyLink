#!/bin/bash
# Adds jira_query support to vporag-deploy wrapper and deploys the staged file.
set -e

WRAPPER="/usr/local/bin/vporag-deploy"
CONNECTORS_DIR="/srv/vpo_rag/Searches/Connectors"

# Add jira_query case to wrapper if not already present
if ! grep -q 'jira_query)' "$WRAPPER"; then
    sed -i '/search_jira)/i\        jira_query)\n            cp /tmp/jira_query.py "$CONNECTORS_DIR/jira_query.py"\n            chown "$OWNER" "$CONNECTORS_DIR/jira_query.py"\n            echo "OK: jira_query.py deployed"\n            deployed=1\n            ;;\n' "$WRAPPER"
    echo "OK: vporag-deploy wrapper updated with jira_query support"
else
    echo "OK: jira_query already in wrapper"
fi

# Deploy the staged file now
cp /tmp/jira_query.py "$CONNECTORS_DIR/jira_query.py"
chown vporag:vporag "$CONNECTORS_DIR/jira_query.py"
echo "OK: jira_query.py deployed to $CONNECTORS_DIR"
grep 'DEFAULT_TOP_DPSTRIAGE' "$CONNECTORS_DIR/jira_query.py"
