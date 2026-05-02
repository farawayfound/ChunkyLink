# -*- coding: utf-8 -*-
"""Profile the live search_kb._run path with timing checkpoints."""
import asyncio, sys, time
sys.path.insert(0, "/srv/vpo_rag/mcp_server")

import search_kb as sk
from pathlib import Path
import config

async def main():
    kb_dir = Path(config.JSON_KB_DIR)
    domains = ["troubleshooting", "queries", "sop"]
    terms = ["seasonal hold", "lineup_id", "lids cache", "stblookup"]

    t0 = time.monotonic()
    domain_chunks, _ = await asyncio.to_thread(sk._load_chunks, kb_dir, domains)
    print(f"_load_chunks:        {time.monotonic()-t0:.2f}s  count:{len(domain_chunks)}")

    t1 = time.monotonic()
    all_chunks = await asyncio.to_thread(sk._load_all_category_chunks, kb_dir)
    print(f"_load_all_chunks:    {time.monotonic()-t1:.2f}s  count:{len(all_chunks)}")

    t2 = time.monotonic()
    all_by_id = {c["id"]: c for c in all_chunks}
    print(f"all_by_id dict:      {time.monotonic()-t2:.2f}s")

    t3 = time.monotonic()
    phase1 = [c for c in domain_chunks if sk._matches_terms(c, terms, min_hits=1)]
    print(f"phase1:              {time.monotonic()-t3:.2f}s  hits:{len(phase1)}")

    t4 = time.monotonic()
    deep_terms = ["queries", "troubleshooting", "lineup", "stb", "channel", "lids", "stblookup"]
    def _deep_hits(c):
        tags = c.get("tags", []); kws = c.get("search_keywords", [])
        sl = c["_sl"]
        return sum(1 for t in deep_terms if t in tags or t in kws or t in sl)
    exclude_ids = {c["id"] for c in phase1}
    phase4 = [c for c in domain_chunks if c["id"] not in exclude_ids and _deep_hits(c) >= 2]
    print(f"phase4:              {time.monotonic()-t4:.2f}s  hits:{len(phase4)}")

    t5 = time.monotonic()
    QUERY_TAG_SET = {"queries", "troubleshooting", "sop"}
    query_chunks = [c for c in all_chunks if QUERY_TAG_SET & set(c.get("tags", []))]
    all_terms_lower = [t.lower() for t in terms + deep_terms]
    phase6 = [c for c in query_chunks if any(t in c["_sl"] for t in all_terms_lower)]
    print(f"phase6:              {time.monotonic()-t5:.2f}s  hits:{len(phase6)}")

    print(f"TOTAL:               {time.monotonic()-t0:.2f}s")

asyncio.run(main())
