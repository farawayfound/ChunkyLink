# -*- coding: utf-8 -*-
import sys, time, re
sys.path.insert(0, "/srv/vpo_rag/mcp_server")
from tools.search_kb import (
    _load_all_category_chunks, _filter_domain_chunks, _set_cached_chunks,
    _get_cached_chunks, _matches_terms, _DEFAULT_DOMAINS, _QUERY_SYNTAX_RE,
    _TAG_STOPLIST, _score_chunk,
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
all_by_id = {c["id"]: c for c in all_chunks}
print(f"all_by_id:   {time.monotonic()-t:.3f}s")

t = time.monotonic()
phase1 = [c for c in domain_chunks if _matches_terms(c, terms, min_hits=1)]
print(f"phase1:      {time.monotonic()-t:.3f}s  hits:{len(phase1)}")

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

t = time.monotonic()
ref_freq = {}
for c in phase1:
    for ref in c.get("related_chunks", []):
        ref_freq[ref] = ref_freq.get(ref, 0) + 1
related_ids = sorted(ref_freq, key=lambda x: -ref_freq[x])[:165]
phase3 = [all_by_id[r] for r in related_ids if r in all_by_id][:55]
print(f"phase3:      {time.monotonic()-t:.3f}s  hits:{len(phase3)}")

t = time.monotonic()
_deep_set = set(deep_terms)
_deep_re  = re.compile("|".join(re.escape(x) for x in deep_terms)) if deep_terms else None
exclude = {c["id"] for c in phase1} | {c["id"] for c in phase3}
def deep_hits(c):
    tags=c.get("tags",[]); kws=c.get("search_keywords",[])
    return sum(1 for x in tags if x in _deep_set) + sum(1 for k in kws if k in _deep_set) + (len(_deep_re.findall(c["_sl"])) if _deep_re else 0)
phase4 = sorted([c for c in domain_chunks if c["id"] not in exclude and deep_hits(c)>=2],
    key=lambda c: -sum(1 for t in c.get("tags",[]) + c.get("search_keywords",[]) if t in _deep_set))[:25]
print(f"phase4:      {time.monotonic()-t:.3f}s  hits:{len(phase4)}")

t = time.monotonic()
cluster_ids = {c.get("topic_cluster_id") for c in phase1 if c.get("topic_cluster_id")}
exclude |= {c["id"] for c in phase4}
phase5 = [c for c in domain_chunks if c.get("topic_cluster_id") in cluster_ids and c["id"] not in exclude and (c.get("cluster_size") or 0)>=3][:20]
print(f"phase5:      {time.monotonic()-t:.3f}s  hits:{len(phase5)}")

t = time.monotonic()
all_terms_lower = [x.lower() for x in list(dict.fromkeys(terms + deep_terms))]
QTS = {"queries","troubleshooting","sop"}
qc = [c for c in all_chunks if QTS & set(c.get("tags",[]))]
exclude |= {c["id"] for c in phase5}
_p6_re = re.compile("|".join(re.escape(x) for x in all_terms_lower))
phase6 = sorted([c for c in qc if c["id"] not in exclude and _p6_re.search(c["_sl"])],
    key=lambda c: -(len(_p6_re.findall(c["_sl"])) + (3 if _QUERY_SYNTAX_RE.search(c["_sl"]) else 0)))[:40]
print(f"phase6:      {time.monotonic()-t:.3f}s  hits:{len(phase6)}")

t = time.monotonic()
all_results = phase1 + phase3 + phase4 + phase5 + phase6
phase1_ids={c["id"] for c in phase1}; phase3_ids={c["id"] for c in phase3}
phase4_ids={c["id"] for c in phase4}; phase6_ids={c["id"] for c in phase6}
scored = []
seen = set()
for chunk in all_results:
    cid = chunk["id"]
    if cid in seen: continue
    seen.add(cid)
    mt = "Initial" if cid in phase1_ids else "Related" if cid in phase3_ids else "DeepDive" if cid in phase4_ids else "Query"
    r = dict(chunk); r["MatchType"]=mt; r["RelevanceScore"]=_score_chunk(chunk,terms,[],discovered,mt)
    scored.append(r)
print(f"score:       {time.monotonic()-t:.3f}s  scored:{len(scored)}")

t = time.monotonic()
STRIP = {"search_text","search_keywords","related_chunks","raw_markdown","topic_cluster_id","cluster_size","text_raw","element_type","_sl"}
slim = [{k:v for k,v in c.items() if k not in STRIP} for c in scored]
print(f"slim:        {time.monotonic()-t:.3f}s")
