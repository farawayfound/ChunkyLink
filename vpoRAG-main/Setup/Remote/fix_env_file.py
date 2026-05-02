#!/usr/bin/env python3
"""Rewrite /etc/vporag/mcp.env with JIRA_PASS safely single-quoted for bash source."""
path = "/etc/vporag/mcp.env"
with open(path, "r") as f:
    lines = f.read().splitlines()

new_lines = []
for line in lines:
    if line.startswith("JIRA_PASS="):
        val = line[len("JIRA_PASS="):]
        # Strip any existing surrounding quotes
        if (val.startswith("'") and val.endswith("'")) or \
           (val.startswith('"') and val.endswith('"')):
            val = val[1:-1]
        # Single-quote the value; escape any embedded single quotes
        val_escaped = val.replace("'", "'\\''")
        new_lines.append(f"JIRA_PASS='{val_escaped}'")
    else:
        new_lines.append(line)

with open(path, "w") as f:
    f.write("\n".join(new_lines) + "\n")

print("Rewritten:")
for l in new_lines:
    if "PASS" in l:
        print(f"  JIRA_PASS=<{len(val)} chars, single-quoted>")
    else:
        print(f"  {l}")
