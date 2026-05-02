# -*- coding: utf-8 -*-
"""Time _search_sync with warm cache — measures true server performance."""
import sys, time
sys.path.insert(0, "/srv/vpo_rag/mcp_server")
from tools.search_kb import (
    _load_all_category_chunks, _filter_domain_chunks, _set_cached_chunks,
    _DEFAULT_DOMAINS, _search_sync, _cache_key, _LEVELS, _PAGE_SIZE,
)
from pathlib import Path
import config

kb = Path(config.JSON_KB_DIR)
terms = ["seasonal hold", "lineup_id", "lids cache", "stblookup"]
query = "seasonal hold lineup mismatch"
level = "Standard"

# Warm the cache
t0 = time.monotonic()
ac = _load_all_category_chunks(kb)
dc, _ = _filter_domain_chunks(ac, _DEFAULT_DOMAINS)
_set_cached_chunks(kb, _DEFAULT_DOMAINS, dc, ac)
print(f"warmup: {time.monotonic()-t0:.2f}s  chunks:{len(ac)}")

# Call _search_sync directly (same path the live server takes)
active_domains = _DEFAULT_DOMAINS
limits = _LEVELS["Standard"]
ckey = _cache_key(terms, query, level, list(active_domains))

t1 = time.monotonic()
r = _search_sync(
    terms, query, level, active_domains,
    limits["Total"], 1, ckey, _PAGE_SIZE,
    limits, False, False, kb, t1
)
elapsed = time.monotonic() - t1
print(f"warm search: {elapsed:.2f}s  chunks:{r.get('total')}  phases:{r.get('phases')}")
print(f"PASS" if elapsed < 30 else f"FAIL — still too slow")
