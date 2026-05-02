# -*- coding: utf-8 -*-
"""
Incremental cross-reference builder
Only updates cross-references for new/modified chunks
"""

import json, logging, sys, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from utils.cross_reference import (
    enrich_chunk_with_cross_refs, 
    build_topic_clusters,
    get_term_aliases,
    auto_generate_aliases
)

def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')

def main():
    out_dir = Path(config.OUT_DIR)
    detail_dir = out_dir / "detail"
    state_file = out_dir / "state" / "processing_state.json"
    
    # Setup logging
    log_path = out_dir / "logs" / "cross_references_incremental.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        filename=str(log_path),
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    logging.getLogger().addHandler(console)
    
    # Check for category files
    category_files = list(detail_dir.glob("chunks.*.jsonl"))
    if not category_files:
        logging.error("No chunk files found. Run indexer first.")
        return
    
    if not state_file.exists():
        logging.error("No processing state found. Run full cross-reference build first.")
        return
    
    start_time = now_iso()
    logging.info(f"Starting incremental cross-reference build at {start_time}")
    
    # Load processing state to identify new/modified docs
    with open(state_file, 'r', encoding='utf-8') as f:
        state = json.load(f)
    
    last_xref_run = state.get("last_cross_reference_run")
    new_doc_ids = set()
    
    for file_key, file_info in state.get("processed_files", {}).items():
        processed_at = file_info.get("processed_at")
        if not last_xref_run or processed_at > last_xref_run:
            new_doc_ids.update(file_info.get("doc_ids", []))
    
    if not new_doc_ids:
        logging.info("No new documents since last cross-reference run.")
        return
    
    logging.info(f"Found {len(new_doc_ids)} new/modified documents")
    
    # Load all chunks from category files
    logging.info("Loading all chunks from category files...")
    all_chunks = []
    new_chunks = []
    
    for category_file in category_files:
        if category_file.name == "chunks.jsonl":  # Skip unified file
            continue
        with open(category_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    chunk = json.loads(line)
                    all_chunks.append(chunk)
                    doc_id = chunk.get("metadata", {}).get("doc_id")
                    if doc_id in new_doc_ids:
                        new_chunks.append(chunk)
    
    logging.info(f"Loaded {len(all_chunks)} total chunks, {len(new_chunks)} new chunks")
    
    # Get config parameters
    max_related = getattr(config, 'MAX_RELATED_CHUNKS', 5)
    min_similarity = getattr(config, 'MIN_SIMILARITY_THRESHOLD', 0.7)
    
    # Get or generate term aliases
    term_aliases = get_term_aliases()
    if not term_aliases:
        logging.info("Auto-generating term aliases from full corpus...")
        term_aliases = auto_generate_aliases(all_chunks)
        logging.info(f"Generated {len(term_aliases)} term alias groups")
    else:
        logging.info(f"Using {len(term_aliases)} term alias groups from config")
    
    # Clear cache before processing
    from utils.cross_reference import _doc_cache
    _doc_cache.clear()
    
    # Rebuild clusters (fast operation)
    logging.info("Rebuilding topic clusters...")
    clusters = build_topic_clusters(all_chunks)
    logging.info(f"Created {len(clusters)} topic clusters")
    
    # Update only new chunks
    logging.info(f"Updating cross-references for {len(new_chunks)} new chunks...")
    chunk_map = {c.get("id"): c for c in all_chunks}
    
    for i, chunk in enumerate(new_chunks):
        if i % 50 == 0 and i > 0:
            logging.info(f"Processing new chunk {i}/{len(new_chunks)}")
        enrich_chunk_with_cross_refs(chunk, all_chunks, clusters, term_aliases, max_related, min_similarity)
        chunk_map[chunk.get("id")] = chunk
    
    # Write back to category files and compile unified
    logging.info("Writing updated chunks by category...")
    from collections import defaultdict
    
    chunks_by_category = defaultdict(list)
    for chunk in chunk_map.values():
        category = chunk.get('metadata', {}).get('nlp_category', 'general')
        chunks_by_category[category].append(chunk)
    
    # Write category files
    for category, chunks in chunks_by_category.items():
        category_file = detail_dir / f"chunks.{category}.jsonl"
        with open(category_file, 'w', encoding='utf-8') as f:
            for chunk in chunks:
                f.write(json.dumps(chunk, ensure_ascii=False) + '\n')
    
    # Compile unified file
    unified_file = detail_dir / "chunks.jsonl"
    with open(unified_file, 'w', encoding='utf-8') as f:
        for chunk in chunk_map.values():
            f.write(json.dumps(chunk, ensure_ascii=False) + '\n')
    logging.info(f"Compiled unified chunks.jsonl")
    
    # Update state
    state["last_cross_reference_run"] = now_iso()
    with open(state_file, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    
    end_time = now_iso()
    logging.info(f"Incremental cross-reference build complete at {end_time}")
    logging.info(f"Updated {len(new_chunks)} chunks")

if __name__ == "__main__":
    main()
