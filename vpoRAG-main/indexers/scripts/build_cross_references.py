# -*- coding: utf-8 -*-
"""
Build cross-references across all indexed chunks
Run after incremental indexing to update relationships
"""

import json, logging, sys, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from utils.cross_reference import (
    enrich_chunk_with_cross_refs, 
    build_topic_clusters,
    auto_generate_aliases,
    get_term_aliases
)

def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')

def main():
    out_dir = Path(config.OUT_DIR)
    detail_dir = out_dir / "detail"
    
    # Setup logging
    log_path = out_dir / "logs" / "cross_references.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        filename=str(log_path),
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    logging.getLogger().addHandler(console)
    
    # Load from category files
    category_files = list(detail_dir.glob("chunks.*.jsonl"))
    if not category_files:
        logging.error("No chunk files found. Run indexer first.")
        return
    
    start_time = now_iso()
    logging.info(f"Starting cross-reference build at {start_time}")
    logging.info("Loading all chunks from category files...")
    
    all_chunks = []
    for category_file in category_files:
        if category_file.name == "chunks.jsonl":  # Skip unified file
            continue
        with open(category_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    all_chunks.append(json.loads(line))
    
    logging.info(f"Loaded {len(all_chunks)} chunks from {len(category_files)-1} category files")
    
    # Get config parameters
    max_related = getattr(config, 'MAX_RELATED_CHUNKS', 5)
    min_similarity = getattr(config, 'MIN_SIMILARITY_THRESHOLD', 0.7)
    
    # Get or generate term aliases
    term_aliases = get_term_aliases()
    if not term_aliases:
        logging.info("No TERM_ALIASES in config - auto-generating from corpus...")
        term_aliases = auto_generate_aliases(all_chunks)
        logging.info(f"Auto-generated {len(term_aliases)} term alias groups")
    else:
        logging.info(f"Using {len(term_aliases)} term alias groups from config")
    
    logging.info(f"Building cross-references (max_related={max_related}, min_similarity={min_similarity})...")
    
    # Build clusters once
    clusters = build_topic_clusters(all_chunks)
    logging.info(f"Created {len(clusters)} topic clusters")
    
    # Clear cache before processing
    from utils.cross_reference import _doc_cache
    _doc_cache.clear()
    
    # Enrich each chunk in-place
    for i, chunk in enumerate(all_chunks):
        if i % 100 == 0 and i > 0:
            logging.info(f"Processing chunk {i}/{len(all_chunks)}")
        enrich_chunk_with_cross_refs(chunk, all_chunks, clusters, term_aliases, max_related, min_similarity)
    
    # Write back to category files and compile unified
    logging.info("Writing enriched chunks by category...")
    from collections import defaultdict
    
    chunks_by_category = defaultdict(list)
    for chunk in all_chunks:
        category = chunk.get('metadata', {}).get('nlp_category', 'general')
        chunks_by_category[category].append(chunk)
    
    # Write category files
    for category, chunks in chunks_by_category.items():
        category_file = detail_dir / f"chunks.{category}.jsonl"
        with open(category_file, 'w', encoding='utf-8') as f:
            for chunk in chunks:
                f.write(json.dumps(chunk, ensure_ascii=False) + '\n')
        logging.info(f"Wrote {len(chunks)} chunks to chunks.{category}.jsonl")
    
    # Compile unified file
    unified_file = detail_dir / "chunks.jsonl"
    with open(unified_file, 'w', encoding='utf-8') as f:
        for chunk in all_chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + '\n')
    logging.info(f"Compiled unified chunks.jsonl with {len(all_chunks)} chunks")
    
    end_time = now_iso()
    logging.info(f"Cross-reference building complete at {end_time}")
    
    # Generate summary
    total_related = sum(len(c.get("related_chunks", [])) for c in all_chunks)
    avg_related = total_related / len(all_chunks) if all_chunks else 0
    logging.info(f"Average related chunks per chunk: {avg_related:.2f}")
    
    # Clear cache after processing
    _doc_cache.clear()

if __name__ == "__main__":
    main()
