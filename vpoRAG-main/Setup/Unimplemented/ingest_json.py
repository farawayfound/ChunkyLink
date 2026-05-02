# D:\vpoRAG\rag_setup\ingest_jsonl.py
import os, json, uuid, requests
from tqdm import tqdm
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm
from pathlib import Path

###CONFIG###
#Make sure to update#
OLLAMA_EMBED = "http://localhost:11434/api/embeddings"
EMBED_MODEL = "mxbai-embed-large"   # or "nomic-embed-text"
QDRANT_URL  = "http://localhost:6333"
BASE = r"C:\vpoRAG\Converted"

def embed_one(text: str):
    # Single-call embedding; supports both response shapes
    r = requests.post(
        OLLAMA_EMBED,
        json={"model": EMBED_MODEL, "prompt": text},
        timeout=120
    )
    r.raise_for_status()
    data = r.json()
    if "embedding" in data:
        return data["embedding"]
    if "embeddings" in data and data["embeddings"]:
        return data["embeddings"][0]
    if "error" in data:
        raise RuntimeError(f"Ollama embeddings error: {data['error']}")
    raise KeyError(f"Unexpected embeddings response: {data}")

def upsert_file(client, collection, records, text_key, payload_fn):
    import uuid
    from qdrant_client.http import models as qm
    for r in tqdm(records, desc=f"Upsert {collection}"):
        text = r[text_key] or ""
        vec = embed_one(text)
        point = qm.PointStruct(
            id=str(uuid.uuid4()),
            vector=vec,
            payload=payload_fn(r),
        )
        client.upsert(collection, points=[point], wait=True)

def load_jsonl(path):
    out=[]
    with open(path, encoding="utf-8") as f:
        for line in f:
            line=line.strip()
            if not line: continue
            out.append(json.loads(line))
    return out

def main():
    qc = QdrantClient(url=QDRANT_URL)

    # 1) DOC-LEVEL ROUTER
    router_docs = load_jsonl(Path(BASE, "router", "router.docs.jsonl"))
    def payload_doc(r):
        return {
            "route_id": r["route_id"],
            "title": r.get("title"),
            "doc_id": r["route_id"].split("::")[0],
            "summary": r.get("summary"),
            "scope_pages": r.get("scope_pages"),
            "tags": r.get("tags", [])
        }
    upsert_file(qc, "vpo_router_docs", router_docs, "summary", payload_doc)

    # 2) CHAPTER ROUTER
    router_chap = load_jsonl(Path(BASE, "router", "router.chapters.jsonl"))
    def payload_chap(r):
        return {
            "route_id": r["route_id"],
            "title": r.get("title"),
            "doc_id": r["route_id"].split("::")[0],
            "chapter_id": r["route_id"].split("::")[1],
            "summary": r.get("summary"),
            "scope_pages": r.get("scope_pages"),
            "tags": r.get("tags", [])
        }
    upsert_file(qc, "vpo_router_chapters", router_chap, "summary", payload_chap)

    # 3) DETAIL (paragraphs & tables)
    detail = load_jsonl(Path(BASE, "detail", "chunks.jsonl"))
    def payload_detail(d):
        m = d["metadata"]
        return {
            "id": d["id"],
            "doc_id": m["doc_id"],
            "chapter_id": m["chapter_id"],
            "element_type": d["element_type"],
            "page_start": m.get("page_start"),
            "page_end": m.get("page_end"),
            "raw_markdown": d.get("raw_markdown"),
            "tags": d.get("tags", []),
            "search_keywords": d.get("search_keywords", []),
            "related_chunks": d.get("related_chunks", []),
            "topic_cluster_id": d.get("topic_cluster_id"),
            "nlp_category": m.get("nlp_category"),
        }
    
    # Use search_text for embedding (flattened searchable content)
    for r in tqdm(detail, desc="Upsert vpo_detail"):
        text = r.get("search_text") or r.get("text") or ""
        vec = embed_one(text)
        point = qm.PointStruct(
            id=str(uuid.uuid4()),
            vector=vec,
            payload=payload_detail(r),
        )
        qc.upsert("vpo_detail", points=[point], wait=True)

if __name__ == "__main__":
    main()
