# -*- coding: utf-8 -*-
import sys, json
sys.path.insert(0, "/srv/vpo_rag/mcp_server")
from tools.search_kb import (
    _load_all_category_chunks, _filter_domain_chunks, _set_cached_chunks,
    _get_cached_chunks, _DEFAULT_DOMAINS,
)
from pathlib import Path
import config, asyncio
from tools import search_kb

kb = Path(config.JSON_KB_DIR)
ac = _load_all_category_chunks(kb)
dc, _ = _filter_domain_chunks(ac, _DEFAULT_DOMAINS)
_set_cached_chunks(kb, _DEFAULT_DOMAINS, dc, ac)

r = asyncio.run(search_kb.run(
    terms=["specnav", "DNCS", "CAS", "bt_dhct_state", "cas_info"],
    query="SpecNav STB commands DNCS CAS package staging",
    level="Quick"
))

chunks = r.get("results", [])
total_chars = sum(len(json.dumps(c)) for c in chunks)
print(f"chunks: {len(chunks)}  total_chars: {total_chars}")
for i, c in enumerate(chunks):
    s = len(json.dumps(c))
    print(f"  [{i}] {s:6d} chars  tags:{c.get('tags',[][:3])[:3]}  id:{c.get('id','')[:60]}")
