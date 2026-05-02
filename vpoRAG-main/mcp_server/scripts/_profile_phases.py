# -*- coding: utf-8 -*-
import sys, time, re
sys.path.insert(0, "/srv/vpo_rag/mcp_server")
from tools.search_kb import (
    _load_all_category_chunks, _filter_domain_chunks, _set_cached_chunks,
    _get_cached_chunks, _matches_terms, _DEFAULT_DOMAINS, _QUERY_SYNTAX_RE,
    _TAG_STOPLIST,
)
from pathlib import Path
import config

kb = Path(config.JSON_KB_DIR)
terms = ["seasonal hold", "lineup_id", "lids cache", "stblookup"]

ac = _load_all_category_chunks(kb)
dc, _ = _filter_domain_chunks(ac, _DEFAULT_DOMAINS)
_set_cached_chunks(kb, _DEFAULT_DOMAINS, dc, ac)
domain_chunks, all_chunks = _get_cached_chunks(kb, _DEFAULT_DOMAINS)

t = time.monotonic()
phase1 = [c for c in domain_chunks if _matches_terms(c, terms, min_hits=1)]
print(f"phase1:  {time.monotonic()-t:.3f}s  hits:{len(phase1)}")

tag_freq = {}
for c in phase1:
    for tag in c.get("tags", []):
        if tag not in _TAG_STOPLIST:
            tag_freq[tag] = tag_freq.get(tag, 0) + 1
top_tags = [x for x,n in sorted(tag_freq.items(), key=lambda x:-x[1]) if n>=2][:15]
kw_freq = {}
for c in phase1:
    for kw in c.get("search_keywords", []):
        if kw and len(kw)>=3: kw_freq[kw] = kw_freq.get(kw,0)+1
discovered = [k for k,n in sorted(kw_freq.items(), key=lambda x:-x[1]) if n>=2][:20]
deep_terms = list(dict.fromkeys(top_tags + discovered))
print(f"phase2:  deep_terms:{len(deep_terms)}")

t = time.monotonic()
_deep_set = set(deep_terms)
_deep_re  = re.compile("|".join(re.escape(x) for x in deep_terms)) if deep_terms else None
exclude = {c["id"] for c in phase1}
def deep_hits(c):
    tags=c.get("tags",[]); kws=c.get("search_keywords",[])
    return sum(1 for x in tags if x in _deep_set) + sum(1 for k in kws if k in _deep_set) + (len(_deep_re.findall(c["_sl"])) if _deep_re else 0)
phase4 = [c for c in domain_chunks if c["id"] not in exclude and deep_hits(c)>=2][:25]
print(f"phase4:  {time.monotonic()-t:.3f}s  hits:{len(phase4)}")

t = time.monotonic()
all_terms = list(dict.fromkeys(terms + deep_terms))
all_terms_lower = [x.lower() for x in all_terms]
QTS = {"queries","troubleshooting","sop"}
qc = [c for c in all_chunks if QTS & set(c.get("tags",[]))]
_p6_re = re.compile("|".join(re.escape(x) for x in all_terms_lower))
phase6 = [c for c in qc if _p6_re.search(c["_sl"])][:40]
print(f"phase6:  {time.monotonic()-t:.3f}s  hits:{len(phase6)}  qc:{len(qc)}")
