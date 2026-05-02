# -*- coding: utf-8 -*-
"""Profile warm-cache search phases to find remaining bottleneck."""
import sys, time
sys.path.insert(0, "/srv/vpo_rag/mcp_server")
from tools.search_kb import (
    _load_all_category_chunks, _filter_domain_chunks, _set_cached_chunks,
    _get_cached_chunks, _matches_terms, _DEFAULT_DOMAINS, _QUERY_SYNTAX_RE,
)
from pathlib import Path
import config

kb = Path(config.JSON_KB_DIR)
terms = ["seasonal hold", "lineup_id", "lids cache", "stblookup"]

# Warm the cache
t0 = time.monotonic()
ac = _load_all_category_chunks(kb)
dc, _ = _filter_domain_chunks(ac, _DEFAULT_DOMAINS)
_set_cached_chunks(kb, _DEFAULT_DOMAINS, dc, ac)
print(f"warmup:      {time.monotonic()-t0:.2f}s  all:{len(ac)} domain:{len(dc)}")

# Now profile each phase using cached data
cc = _get_cached_chunks(kb, _DEFAULT_DOMAINS)
domain_chunks, all_chunks = cc
all_by_id = {c["id"]: c for c in all_chunks}

t1 = time.monotonic()
phase1 = [c for c in domain_chunks if _matches_terms(c, terms, min_hits=1)]
print(f"phase1:      {time.monotonic()-t1:.3f}s  hits:{len(phase1)}")

# Phase 2
tag_freq = {}
for c in phase1:
    for tag in c.get("tags", []):
        tag_freq[tag] = tag_freq.get(tag, 0) + 1
top_tags = [t for t, n in sorted(tag_freq.items(), key=lambda x: -x[1]) if n >= 2][:15]
kw_freq = {}
for c in phase1:
    for kw in c.get("search_keywords", []):
        if kw and len(kw) >= 3:
            kw_freq[kw] = kw_freq.get(kw, 0) + 1
discovered = [k for k, n in sorted(kw_freq.items(), key=lambda x: -x[1]) if n >= 2][:20]
deep_terms = list(dict.fromkeys(top_tags + discovered))
print(f"phase2:      deep_terms:{len(deep_terms)}")

t2 = time.monotonic()
ref_freq = {}
for c in phase1:
    for ref in c.get("related_chunks", []):
        ref_freq[ref] = ref_freq.get(ref, 0) + 1
related_ids = sorted(ref_freq, key=lambda x: -ref_freq[x])[:165]
phase3 = [all_by_id[r] for r in related_ids if r in all_by_id][:55]
print(f"phase3:      {time.monotonic()-t2:.3f}s  hits:{len(phase3)}")

t3 = time.monotonic()
exclude = {c["id"] for c in phase1} | {c["id"] for c in phase3}
def deep_hits(c):
    tags = c.get("tags", []); kws = c.get("search_keywords", []); sl = c["_sl"]
    return sum(1 for t in deep_terms if t in tags or t in kws or t in sl)
phase4 = sorted(
    [c for c in domain_chunks if c["id"] not in exclude and deep_hits(c) >= 2],
    key=lambda c: -sum(1 for t in deep_terms if t in c.get("tags", []) or t in c.get("search_keywords", []))
)[:25]
print(f"phase4:      {time.monotonic()-t3:.3f}s  hits:{len(phase4)}")

t4 = time.monotonic()
cluster_ids = {c.get("topic_cluster_id") for c in phase1 if c.get("topic_cluster_id")}
exclude |= {c["id"] for c in phase4}
phase5 = [c for c in domain_chunks
          if c.get("topic_cluster_id") in cluster_ids and c["id"] not in exclude
          and (c.get("cluster_size") or 0) >= 3][:20]
print(f"phase5:      {time.monotonic()-t4:.3f}s  hits:{len(phase5)}")

t5 = time.monotonic()
all_terms = list(dict.fromkeys(terms + deep_terms))
all_terms_lower = [t.lower() for t in all_terms]
exclude |= {c["id"] for c in phase5}
QTS = {"queries", "troubleshooting", "sop"}
qc = [c for c in all_chunks if QTS & set(c.get("tags", []))]
def p6score(c):
    sl = c["_sl"]
    return sum(1 for t in all_terms_lower if t in sl) + (3 if _QUERY_SYNTAX_RE.search(sl) else 0)
phase6 = sorted(
    [c for c in qc if c["id"] not in exclude and any(t in c["_sl"] for t in all_terms_lower)],
    key=lambda c: -p6score(c)
)[:40]
print(f"phase6:      {time.monotonic()-t5:.3f}s  hits:{len(phase6)}")

print(f"TOTAL logic: {time.monotonic()-t1:.2f}s")
print(f"TOTAL incl warmup: {time.monotonic()-t0:.2f}s")
