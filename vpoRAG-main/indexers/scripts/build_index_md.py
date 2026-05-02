# -*- coding: utf-8 -*-
"""
Markdown-based VPO RAG Indexer
Outputs searchable Markdown files to MD/ directory
Usage: python build_index_md.py
"""

import os, re, json, hashlib, datetime, logging, sys
from pathlib import Path
from typing import List, Dict, Any

sys.path.insert(0, str(Path(__file__).parent))
import config
from core.incremental_indexer import IncrementalIndexer
from utils.topic_metadata import add_topic_metadata
from utils.text_processing import classify_profile, summarize_for_router, normalize_text, extract_content_tags
from utils.nlp_classifier import enrich_record_with_nlp
from utils.cross_reference import build_topic_clusters, get_term_aliases, auto_generate_aliases, enrich_chunk_with_cross_refs
from processors.pdf_processor import build_for_pdf
from processors.text_processor import build_for_txt, build_for_docx, build_for_pptx
from processors.csv_processor import build_for_csv

def sha8(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()[:8]

def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')

def ensure_dirs():
    for p in [
        Path(config.OUT_DIR, "detail"),
        Path(config.OUT_DIR, "router"),
        Path(config.OUT_DIR, "logs"),
        Path(config.OUT_DIR, "state"),
    ]:
        p.mkdir(parents=True, exist_ok=True)

ensure_dirs()
log_path = Path(config.OUT_DIR, "logs", "build_index.log")
logging.basicConfig(
    filename=str(log_path),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
logging.getLogger().addHandler(console)

def chunk_to_markdown(chunk: Dict) -> str:
    """Convert chunk to Markdown format"""
    md = []
    md.append(f"## {chunk.get('id', 'unknown')}\n")
    
    # Metadata section
    meta = chunk.get('metadata', {})
    md.append("**Metadata:**")
    md.append(f"- Document: `{meta.get('doc_id', 'N/A')}`")
    md.append(f"- Category: `{meta.get('nlp_category', 'general')}`")
    if meta.get('breadcrumb'):
        md.append(f"- Breadcrumb: {meta.get('breadcrumb')}")
    if meta.get('page_start'):
        md.append(f"- Pages: {meta.get('page_start')}-{meta.get('page_end')}")
    
    # Tags
    tags = chunk.get('tags', [])
    if tags:
        md.append(f"- Tags: {', '.join(f'`{t}`' for t in tags)}")
    
    # Related chunks
    related = chunk.get('related_chunks', [])
    if related:
        md.append(f"- Related: {len(related)} chunks")
    
    md.append("")
    
    # Content
    md.append("**Content:**\n")
    md.append(chunk.get('text', ''))
    md.append("\n---\n")
    
    return "\n".join(md)

def write_chunks_by_category(all_chunks: List[Dict], detail_dir: Path):
    """Write chunks to category-specific Markdown files"""
    from collections import defaultdict
    
    chunks_by_category = defaultdict(list)
    for chunk in all_chunks:
        category = chunk.get('metadata', {}).get('nlp_category', 'general')
        chunks_by_category[category].append(chunk)
    
    # Write category files
    for category, chunks in chunks_by_category.items():
        category_file = detail_dir / f"chunks.{category}.md"
        with open(category_file, 'w', encoding='utf-8') as f:
            f.write(f"# {category.upper()} Knowledge Base\n\n")
            f.write(f"Total chunks: {len(chunks)}\n\n")
            f.write("---\n\n")
            for chunk in chunks:
                f.write(chunk_to_markdown(chunk))
        logging.info(f"Wrote {len(chunks)} chunks to chunks.{category}.md")
    
    # Unified file
    unified_file = detail_dir / "chunks.md"
    with open(unified_file, 'w', encoding='utf-8') as f:
        f.write(f"# Unified Knowledge Base\n\n")
        f.write(f"Total chunks: {len(all_chunks)}\n\n")
        f.write("---\n\n")
        for chunk in all_chunks:
            f.write(chunk_to_markdown(chunk))
    logging.info(f"Wrote {len(all_chunks)} chunks to unified chunks.md")

def main():
    ensure_dirs()
    
    # Use JSONindexers' incremental tracker but with MD OUT_DIR
    indexer = IncrementalIndexer(config.OUT_DIR)
    files_by_status = indexer.get_files_to_process(config.SRC_DIR)
    files_to_process = files_by_status["new"] + files_by_status["modified"]
    
    if not files_to_process:
        logging.info("No new or modified files to process.")
        return
    
    logging.info(f"Processing {len(files_to_process)} files")
    
    all_detail = []

    for path in files_to_process:
        if path in files_by_status["modified"]:
            old_doc_ids = indexer.get_existing_doc_ids(path)
            if old_doc_ids:
                indexer.remove_old_records(old_doc_ids)
        
        prof = "auto" if getattr(config, 'ENABLE_AUTO_CLASSIFICATION', False) else classify_profile(path.name)
        logging.info(f"Processing [{prof}] {path}")

        try:
            if path.suffix.lower() == ".pdf":
                res = build_for_pdf(path, vars(config))
                for record in res["detail"]:
                    enriched = enrich_record_with_nlp(add_topic_metadata(record, path), record.get("text_raw", record.get("text", "")))
                    if enriched.get("metadata", {}).get("nlp_category"):
                        nlp_cat = enriched["metadata"]["nlp_category"]
                        enriched["tags"] = [nlp_cat] + [t for t in enriched.get("tags", []) if t != nlp_cat]
                    all_detail.append(enriched)
            
            elif path.suffix.lower() == ".pptx":
                res = build_for_pptx(path, vars(config))
                for record in res["detail"]:
                    enriched = enrich_record_with_nlp(add_topic_metadata(record, path), record.get("text_raw", record.get("text", "")))
                    if enriched.get("metadata", {}).get("nlp_category"):
                        nlp_cat = enriched["metadata"]["nlp_category"]
                        enriched["tags"] = [nlp_cat] + [t for t in enriched.get("tags", []) if t != nlp_cat]
                    all_detail.append(enriched)
            
            elif path.suffix.lower() == ".docx":
                res = build_for_docx(path, vars(config))
                for record in res["detail"]:
                    enriched = enrich_record_with_nlp(add_topic_metadata(record, path), record.get("text_raw", ""))
                    if enriched.get("metadata", {}).get("nlp_category"):
                        nlp_cat = enriched["metadata"]["nlp_category"]
                        enriched["tags"] = [nlp_cat] + [t for t in enriched.get("tags", []) if t != nlp_cat]
                    all_detail.append(enriched)
            
            elif path.suffix.lower() == ".txt":
                res = build_for_txt(path, vars(config))
                for record in res["detail"]:
                    enriched = enrich_record_with_nlp(add_topic_metadata(record, path), record.get("text_raw", ""))
                    if enriched.get("metadata", {}).get("nlp_category"):
                        nlp_cat = enriched["metadata"]["nlp_category"]
                        enriched["tags"] = [nlp_cat] + [t for t in enriched.get("tags", []) if t != nlp_cat]
                    all_detail.append(enriched)
            
            elif path.suffix.lower() == ".csv":
                res = build_for_csv(path, vars(config))
                for record in res["detail"]:
                    enriched = enrich_record_with_nlp(add_topic_metadata(record, path), record.get("text_raw", ""))
                    if enriched.get("metadata", {}).get("nlp_category"):
                        nlp_cat = enriched["metadata"]["nlp_category"]
                        enriched["tags"] = [nlp_cat] + [t for t in enriched.get("tags", []) if t != nlp_cat]
                    all_detail.append(enriched)
        
        except Exception as ex:
            logging.exception(f"Error processing {path.name}: {ex}")
        
        indexer.mark_processed(path, [path.name])

    # Build cross-references if enabled
    if getattr(config, 'ENABLE_CROSS_REFERENCES', True) and all_detail:
        logging.info(f"Building cross-references for {len(all_detail)} chunks...")
        
        term_aliases = get_term_aliases()
        if not term_aliases:
            term_aliases = auto_generate_aliases(all_detail)
        
        clusters = build_topic_clusters(all_detail)
        
        # Add cross-ref metadata
        for chunk in all_detail:
            enrich_chunk_with_cross_refs(chunk, all_detail, clusters, term_aliases, 
                                        getattr(config, 'MAX_RELATED_CHUNKS', 5),
                                        getattr(config, 'MIN_SIMILARITY_THRESHOLD', 0.7))

    # Write Markdown files
    detail_dir = Path(config.OUT_DIR) / "detail"
    write_chunks_by_category(all_detail, detail_dir)
    
    indexer.finalize_run()
    logging.info(f"Markdown indexing complete. Processed {len(files_to_process)} files.")

if __name__ == "__main__":
    main()
