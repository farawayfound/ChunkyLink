# -*- coding: utf-8 -*-
"""Profile search_kb phase timings to find the bottleneck."""
import time, json, re
from pathlib import Path

KB = Path("/srv/vpo_rag/JSON/detail")
terms = ["seasonal hold", "lineup_id", "lids cache", "stblookup"]
deep_terms = ["queries", "troubleshooting", "lineup", "stb", "channel"]

t0 = time.monotonic()
chunks = [json.loads(l) for f in KB.glob("chunks.*.jsonl")
          for l in open(f, encoding="utf-8") if l.strip() and f.name != "chunks.jsonl"]
print(f"load:        {time.monotonic()-t0:.2f}s  count:{len(chunks)}")

t1 = time.monotonic()
for c in chunks:
    c["_sl"] = ((c.get("text") or "") + " " + (c.get("search_text") or "")[:500]).lower()
print(f"_sl build:   {time.monotonic()-t1:.2f}s")

t2 = time.monotonic()
domain_chunks = [c for c in chunks if any(tag in c.get("tags", [])
                 for tag in ("troubleshooting", "queries", "sop"))]
phase1 = [c for c in domain_chunks if sum(1 for t in terms if t.lower() in c["_sl"]) >= 1]
print(f"phase1:      {time.monotonic()-t2:.2f}s  hits:{len(phase1)}")

t3 = time.monotonic()
def deep_hits(c):
    tags = c.get("tags", []); kws = c.get("search_keywords", [])
    sl = c["_sl"]
    return sum(1 for t in deep_terms if t in tags or t in kws or t in sl)

phase4 = [c for c in domain_chunks if deep_hits(c) >= 2]
print(f"phase4:      {time.monotonic()-t3:.2f}s  hits:{len(phase4)}")

t4 = time.monotonic()
QUERY_TAG_SET = {"queries", "troubleshooting", "sop"}
query_chunks = [c for c in chunks if QUERY_TAG_SET & set(c.get("tags", []))]
all_terms_lower = [t.lower() for t in terms + deep_terms]
phase6 = [c for c in query_chunks if any(t in c["_sl"] for t in all_terms_lower)]
print(f"phase6:      {time.monotonic()-t4:.2f}s  hits:{len(phase6)}")

t5 = time.monotonic()
long_terms = [t for t in terms if len(t) >= 5]
prefixes = [t[:5] for t in long_terms]
phase7 = [c for c in domain_chunks if sum(1 for p in prefixes if p in c["_sl"]) >= 2]
print(f"phase7:      {time.monotonic()-t5:.2f}s  hits:{len(phase7)}")

print(f"TOTAL:       {time.monotonic()-t0:.2f}s")
