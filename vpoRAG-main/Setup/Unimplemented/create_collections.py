# D:\vpoRAG\rag_setup\create_collections.py
import requests, sys
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

OLLAMA_EMBED = "http://localhost:11434/api/embeddings"
EMBED_MODEL = "mxbai-embed-large"  # or "nomic-embed-text"
QDRANT_URL = "http://localhost:6333"

def ensure_collection(qc: QdrantClient, name: str, dim: int):
    if qc.collection_exists(name):
        # You can keep existing collections; or drop & recreate for clean runs:
        qc.delete_collection(name)
    qc.create_collection(
        collection_name=name,
        vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE),
        optimizers_config=qm.OptimizersConfigDiff(indexing_threshold=1000),
    )
    # Payload indexes for filtering
    for field in ("doc_id", "chapter_id", "element_type", "topic_cluster_id", "nlp_category"):
        try:
            qc.create_payload_index(name, field_name=field, field_schema=qm.PayloadSchemaType.KEYWORD)
        except Exception:
            pass

def get_dim():
    # Be compatible with both response shapes: {"embedding":[...]} or {"embeddings":[[...]]}
    r = requests.post(
        OLLAMA_EMBED,
        json={"model": EMBED_MODEL, "prompt": "probe dimension"},  # "prompt" works everywhere
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    if "embedding" in data and isinstance(data["embedding"], list):
        return len(data["embedding"])
    if "embeddings" in data and isinstance(data["embeddings"], list) and data["embeddings"]:
        return len(data["embeddings"][0])
    if "error" in data:
        raise RuntimeError(f"Ollama embeddings error: {data['error']}")
    raise KeyError(f"Unexpected embeddings response shape: {data}")

def main():
    dim = get_dim()
    print("Embedding dim:", dim)
    qc = QdrantClient(url=QDRANT_URL, timeout=60.0)
    for name in ["vpo_router_docs","vpo_router_chapters","vpo_detail"]:
        ensure_collection(qc, name, dim)
if __name__ == "__main__":
    main()
