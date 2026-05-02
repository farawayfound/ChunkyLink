# D:\vpoRAG\rag_setup\chat_rag.py
import requests, json, re
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

###CONFIG###
#Make sure to update#
QDRANT_URL = "http://localhost:6333"
OLLAMA_CHAT = "http://localhost:11434/api/chat"
GEN_MODEL = "deepseek-r1:8b"
EMBED_API = "http://localhost:11434/api/embeddings"
EMBED_MODEL = "mxbai-embed-large"

def embed(text):
    r = requests.post(EMBED_API, json={"model": EMBED_MODEL, "input": text})
    r.raise_for_status()
    return r.json()["embeddings"][0]

def search(qc, collection, query_vec, limit=8, must=None):
    return qc.search(
        collection_name=collection,
        query_vector=query_vec,
        limit=limit,
        query_filter=qm.Filter(must=must) if must else None
    )

def pick_tables_first(hits):
    # light heuristic: push tables up when user asks for numbers/steps
    return sorted(hits, key=lambda h: (0 if h.payload.get("element_type")=="table" else 1, -h.score))

def build_context(detail_hits, qc, max_chars=5000):
    chunks=[]
    used=0
    seen_ids = set()
    
    for h in detail_hits:
        m = h.payload
        chunk_id = m.get('id')
        if chunk_id in seen_ids:
            continue
        seen_ids.add(chunk_id)
        
        prefix = f"[{m.get('doc_id')} · {m.get('chapter_id')} · p{m.get('page_start')}]"
        text = m.get("raw_markdown") or "(content)"
        block = f"{prefix}\n{text}"
        
        if used + len(block) > max_chars:
            break
        chunks.append(block)
        used += len(block)
        
        # Expand with related chunks
        related = m.get("related_chunks", [])[:2]
        for rel_id in related:
            if used >= max_chars or rel_id in seen_ids:
                continue
            try:
                rel_hits = qc.scroll(
                    collection_name="vpo_detail",
                    scroll_filter=qm.Filter(must=[qm.FieldCondition(key="id", match=qm.MatchValue(value=rel_id))]),
                    limit=1
                )
                if rel_hits[0]:
                    rel_payload = rel_hits[0][0].payload
                    seen_ids.add(rel_id)
                    rel_text = rel_payload.get("raw_markdown") or "(content)"
                    rel_block = f"[Related: {rel_payload.get('doc_id')} · p{rel_payload.get('page_start')}]\n{rel_text}"
                    if used + len(rel_block) <= max_chars:
                        chunks.append(rel_block)
                        used += len(rel_block)
            except:
                pass
    
    return "\n\n---\n\n".join(chunks)

def chat_llm(question, context):
    sys_prompt = (
      "You are VPO Assistant. Use the provided knowledge base context ONLY. "
      "Cite doc_id + page for each key fact. Render tables as-is when provided. "
      "If unsure, say so and suggest where to look."
    )
    messages = [
        {"role":"system","content":sys_prompt},
        {"role":"user","content":f"Question:\n{question}\n\nContext:\n{context}"}
    ]
    r = requests.post(OLLAMA_CHAT, json={"model": GEN_MODEL, "messages": messages, "stream": False})
    r.raise_for_status()
    return r.json()["message"]["content"]

def answer(q):
    qc = QdrantClient(url=QDRANT_URL)
    qv = embed(q)

    # Direct detail search (leverages search_text embeddings)
    detail_hits = search(qc, "vpo_detail", qv, limit=15)
    
    # Cluster expansion
    cluster_ids = set()
    for h in detail_hits[:5]:
        cid = h.payload.get("topic_cluster_id")
        if cid:
            cluster_ids.add(cid)
    
    for cid in cluster_ids:
        cluster_hits = search(
            qc, "vpo_detail", qv, limit=5,
            must=[qm.FieldCondition(key="topic_cluster_id", match=qm.MatchValue(value=cid))]
        )
        detail_hits.extend(cluster_hits)
    
    detail_ranked = pick_tables_first(detail_hits)[:12]
    ctx = build_context(detail_ranked, qc)
    return chat_llm(q, ctx)

if __name__ == "__main__":
    while True:
        q = input("\nAsk VPO Assistant > ").strip()
        if not q: continue
        print("\n---\n", answer(q), "\n---")
