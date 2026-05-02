# -*- coding: utf-8 -*-
"""
Enhanced VPO RAG Indexer with Incremental Processing
- Only processes new/modified files
- Maintains existing vector database structure
- Supports topic-based organization
"""

import os, io, re, json, math, hashlib, datetime, logging, sys
from pathlib import Path
from typing import List, Dict, Any, Tuple

# Support both package and direct execution
try:
    # Try package imports first (when run as: python -m indexers.scripts.build_index_incremental)
    from indexers import config
    from indexers.core.incremental_indexer import IncrementalIndexer
    from indexers.utils.topic_metadata import add_topic_metadata
    from indexers.utils.text_processing import classify_profile, summarize_for_router, normalize_text, extract_content_tags
    from indexers.utils.nlp_classifier import enrich_record_with_nlp
    from indexers.processors.pdf_processor import build_for_pdf
    from indexers.processors.text_processor import build_for_txt, build_for_docx, build_for_pptx
except ImportError:
    # Fall back to direct imports (when run as: cd indexers/scripts && python build_index_incremental.py)
    sys.path.insert(0, str(Path(__file__).parent.parent))
    import config
    from core.incremental_indexer import IncrementalIndexer
    from utils.topic_metadata import add_topic_metadata
    from utils.text_processing import classify_profile, summarize_for_router, normalize_text, extract_content_tags
    from utils.nlp_classifier import enrich_record_with_nlp
    from processors.pdf_processor import build_for_pdf
    from processors.text_processor import build_for_txt, build_for_docx, build_for_pptx

def sha8(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()[:8]

def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')

def ensure_dirs():
    for p in [
        Path(config.OUT_DIR, "detail"),
        Path(config.OUT_DIR, "router"),
        Path(config.OUT_DIR, "logs"),
        Path(config.OUT_DIR, "manifests"),
        Path(config.OUT_DIR, "state"),
    ]:
        p.mkdir(parents=True, exist_ok=True)

# Setup logging
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

try:
    import fitz
    fitz.TOOLS.mupdf_display_errors(False)  # Suppress PDF parsing warnings
except Exception as e:
    raise SystemExit("Please install PyMuPDF: pip install pymupdf") from e



def split_with_overlap(words: List[str], target_tokens: int, overlap_tokens: int) -> List[str]:
    out = []; i = 0
    while i < len(words):
        j = min(len(words), i + target_tokens)
        out.append(" ".join(words[i:j]).strip())
        if j >= len(words): break
        i = max(j - overlap_tokens, i + 1)
    return out

def split_glossary_entries(text: str) -> List[dict]:
    entries = []
    for line in re.split(r"[\r\n]+", text):
        line = line.strip()
        if not line: continue
        m = re.match(r"^([A-Za-z0-9\/\-\(\)\s]{2,40})\s*[-–:]\s*(.+)$", line)
        if m:
            term, definition = m.group(1).strip(), m.group(2).strip()
            entries.append((term, definition))
    chunks = []
    for term, definition in entries:
        part = f"{term}: {definition}"
        chunks.append({
            "id": f"gloss::{sha8(part)}",
            "text": part,
            "element_type": "glossary",
            "metadata": {
                "doc_id": None,
                "chapter_title": "Glossary",
                "chapter_id": "glossary",
                "section_title": term,
                "section_id": None,
                "page_start": None, "page_end": None, "bbox": None, "term": term
            },
            "raw_markdown": None
        })
    return chunks

def near_duplicate(a_text: str, b_text: str) -> bool:
    try:
        from rapidfuzz import fuzz
        a = " ".join(a_text.split())[:20000]
        b = " ".join(b_text.split())[:20000]
        return fuzz.token_set_ratio(a, b) >= 90
    except Exception:
        return False

def main():
    ensure_dirs()
    
    # Initialize incremental indexer
    indexer = IncrementalIndexer(config.OUT_DIR)
    
    # Get files to process (only new/modified)
    files_by_status = indexer.get_files_to_process(config.SRC_DIR)
    files_to_process = files_by_status["new"] + files_by_status["modified"]
    
    if not files_to_process:
        logging.info("No new or modified files to process.")
        return
    
    logging.info(f"Processing {len(files_to_process)} files ({len(files_by_status['new'])} new, {len(files_by_status['modified'])} modified)")
    
    all_router_docs, all_router_chapters, all_detail = [], [], []
    manifest = {"started": now_iso(), "files": [], "out_dir": config.OUT_DIR, "totals": {}}
    sop_buckets = {}

    for path in files_to_process:
        # Remove old records for modified files
        if path in files_by_status["modified"]:
            old_doc_ids = indexer.get_existing_doc_ids(path)
            if old_doc_ids:
                indexer.remove_old_records(old_doc_ids)
                logging.info(f"Removed old records for modified file: {path.name}")
        
        # Use NLP classification if enabled, otherwise use filename-based
        if getattr(config, 'ENABLE_AUTO_CLASSIFICATION', False):
            prof = "auto"  # Will be determined by NLP
        else:
            prof = classify_profile(path.name)
        logging.info(f"Processing [{prof}] {path}")

        if path.suffix.lower() == ".pptx":
            try:
                res = build_for_pptx(path, vars(config))
                full_text = " ".join([r["summary"] for r in res["router"]])[:5000]
                for record in res["router"]:
                    enriched = enrich_record_with_nlp(add_topic_metadata(record, path), record.get("summary", ""))
                    if enriched.get("metadata", {}).get("nlp_category"):
                        nlp_cat = enriched["metadata"]["nlp_category"]
                        enriched["tags"] = [nlp_cat] + [t for t in enriched.get("tags", []) if t != nlp_cat]
                    all_router_chapters.append(enriched)
                
                doc_record = {
                    "route_id": f"{path.name}::doc",
                    "title": path.stem,
                    "scope_pages": [1, len(res["router"])],
                    "summary": summarize_for_router(full_text, config.MAX_ROUTER_SUMMARY_CHARS),
                    "tags": [prof]
                }
                all_router_docs.append(enrich_record_with_nlp(add_topic_metadata(doc_record, path), full_text))
                
                for record in res["detail"]:
                    enriched = enrich_record_with_nlp(add_topic_metadata(record, path), record.get("text_raw", record.get("text", "")))
                    if enriched.get("metadata", {}).get("nlp_category"):
                        nlp_cat = enriched["metadata"]["nlp_category"]
                        enriched["tags"] = [nlp_cat] + [t for t in enriched.get("tags", []) if t != nlp_cat]
                    all_detail.append(enriched)
            except Exception as ex:
                logging.exception(f"PPTX error {path.name}: {ex}")

        elif path.suffix.lower() == ".pdf":
            try:
                # Check for glossary (special handling needed)
                if prof == "glossary" or "glossary" in path.name.lower():
                    doc = fitz.open(str(path))
                    text = " ".join([normalize_text(pg.get_text("text")) for pg in doc])
                    gloss_chunks = split_glossary_entries(text)
                    doc_record = {
                        "route_id": f"{path.name}::doc",
                        "title": path.stem,
                        "scope_pages": [1, doc.page_count],
                        "summary": summarize_for_router(text, config.MAX_ROUTER_SUMMARY_CHARS),
                        "tags": ["glossary"]
                    }
                    all_router_docs.append(add_topic_metadata(doc_record, path))
                    
                    for c in gloss_chunks:
                        c["metadata"]["doc_id"] = path.name
                        enriched = enrich_record_with_nlp(add_topic_metadata(c, path), c.get("text", ""))
                        if enriched.get("metadata", {}).get("nlp_category"):
                            nlp_cat = enriched["metadata"]["nlp_category"]
                            enriched["tags"] = [nlp_cat] + [t for t in enriched.get("tags", []) if t != nlp_cat]
                        all_detail.append(enriched)
                    doc.close()
                else:
                    res = build_for_pdf(path, vars(config))
                    full_text = " ".join([r["summary"] for r in res["router"]])[:4000]
                    for record in res["router"]:
                        enriched = enrich_record_with_nlp(add_topic_metadata(record, path), record.get("summary", ""))
                        if enriched.get("metadata", {}).get("nlp_category"):
                            nlp_cat = enriched["metadata"]["nlp_category"]
                            enriched["tags"] = [nlp_cat] + [t for t in enriched.get("tags", []) if t != nlp_cat]
                        all_router_chapters.append(enriched)
                    
                    content_tags = extract_content_tags(full_text)
                    doc_record = {
                        "route_id": f"{path.name}::doc",
                        "title": path.stem,
                        "scope_pages": [1, res["pages"]],
                        "summary": summarize_for_router(full_text, config.MAX_ROUTER_SUMMARY_CHARS),
                        "tags": [prof] + content_tags
                    }
                    all_router_docs.append(enrich_record_with_nlp(add_topic_metadata(doc_record, path), full_text))
                    
                    for record in res["detail"]:
                        enriched = enrich_record_with_nlp(add_topic_metadata(record, path), record.get("text_raw", record.get("text", "")))
                        if enriched.get("metadata", {}).get("nlp_category"):
                            nlp_cat = enriched["metadata"]["nlp_category"]
                            enriched["tags"] = [nlp_cat] + [t for t in enriched.get("tags", []) if t != nlp_cat]
                        all_detail.append(enriched)
                    
                    # SOP deduplication (check filename or NLP category)
                    if prof == "sop" or "sop" in path.name.lower():
                        base = re.sub(r"v\d+|\d{8}_\d{6}", "", path.stem, flags=re.I).strip().lower()
                        sop_buckets.setdefault(base, []).append(path)
            except Exception as ex:
                logging.exception(f"PDF error {path.name}: {ex}")
                continue

        elif path.suffix.lower() == ".txt":
            try:
                res = build_for_txt(path, vars(config))
                full_text = res["router"][0]["summary"] if res["router"] else ""
                for record in res["router"]:
                    enriched = enrich_record_with_nlp(add_topic_metadata(record, path), record.get("summary", ""))
                    if enriched.get("metadata", {}).get("nlp_category"):
                        nlp_cat = enriched["metadata"]["nlp_category"]
                        enriched["tags"] = [nlp_cat] + [t for t in enriched.get("tags", []) if t != nlp_cat]
                    all_router_chapters.append(enriched)
                for record in res["detail"]:
                    enriched = enrich_record_with_nlp(add_topic_metadata(record, path), record.get("text_raw", ""))
                    if enriched.get("metadata", {}).get("nlp_category"):
                        nlp_cat = enriched["metadata"]["nlp_category"]
                        enriched["tags"] = [nlp_cat] + [t for t in enriched.get("tags", []) if t != nlp_cat]
                    all_detail.append(enriched)
                
                # Add doc-level router
                doc_record = {
                    "route_id": f"{path.name}::doc",
                    "title": path.stem,
                    "scope_pages": [1, 1],
                    "summary": full_text,
                    "tags": [prof]
                }
                all_router_docs.append(enrich_record_with_nlp(add_topic_metadata(doc_record, path), full_text))
            except Exception as ex:
                logging.exception(f"TXT error {path.name}: {ex}")

        elif path.suffix.lower() == ".docx":
            try:
                res = build_for_docx(path, vars(config))
                full_text = " ".join([r["summary"] for r in res["router"]])[:4000]
                for record in res["router"]:
                    enriched = enrich_record_with_nlp(add_topic_metadata(record, path), record.get("summary", ""))
                    if enriched.get("metadata", {}).get("nlp_category"):
                        nlp_cat = enriched["metadata"]["nlp_category"]
                        enriched["tags"] = [nlp_cat] + [t for t in enriched.get("tags", []) if t != nlp_cat]
                    all_router_chapters.append(enriched)
                for record in res["detail"]:
                    enriched = enrich_record_with_nlp(add_topic_metadata(record, path), record.get("text_raw", ""))
                    if enriched.get("metadata", {}).get("nlp_category"):
                        nlp_cat = enriched["metadata"]["nlp_category"]
                        enriched["tags"] = [nlp_cat] + [t for t in enriched.get("tags", []) if t != nlp_cat]
                    all_detail.append(enriched)
                
                # Add doc-level router
                doc_record = {
                    "route_id": f"{path.name}::doc",
                    "title": path.stem,
                    "scope_pages": [1, len(res["router"])],
                    "summary": summarize_for_router(full_text, config.MAX_ROUTER_SUMMARY_CHARS),
                    "tags": [prof]
                }
                all_router_docs.append(enrich_record_with_nlp(add_topic_metadata(doc_record, path), full_text))
            except Exception as ex:
                logging.exception(f"DOCX error {path.name}: {ex}")

        manifest["files"].append({"file": path.name, "profile": prof})
        
        # Mark file as processed
        doc_ids = [path.name]
        indexer.mark_processed(path, doc_ids)

    # SOP deduplication
    pruned_ids = set()
    for base, paths in sop_buckets.items():
        if len(paths) >= 2:
            paths = sorted(paths, key=lambda p: p.stat().st_mtime, reverse=True)
            keep, others = paths[0], paths[1:]
            try:
                doc_keep = fitz.open(str(keep))
                text_keep = " ".join([normalize_text(pg.get_text("text")) for pg in doc_keep.pages[:10]])
                for o in others:
                    doc_o = fitz.open(str(o))
                    text_o = " ".join([normalize_text(pg.get_text("text")) for pg in doc_o.pages[:10]])
                    if near_duplicate(text_keep, text_o):
                        pruned_ids.add(o.name)
                        logging.info(f"Near-duplicate SOP pruned: {o.name} (keeping {keep.name})")
            except Exception:
                pass
    
    # Filter pruned docs from detail records
    if pruned_ids:
        all_detail = [d for d in all_detail if d["metadata"].get("doc_id") not in pruned_ids]
        all_router_docs = [r for r in all_router_docs if r["route_id"].split("::")[0] not in pruned_ids]
        all_router_chapters = [r for r in all_router_chapters if r["route_id"].split("::")[0] not in pruned_ids]

    # Append new records to existing files (incremental)
    new_records = {
        "router_docs": all_router_docs,
        "router_chapters": all_router_chapters,
        "detail": all_detail
    }
    
    indexer.append_new_records(new_records)
    
    # Split unified index into category files
    detail_dir = Path(config.OUT_DIR) / "detail"
    unified_file = detail_dir / "chunks.jsonl"
    if unified_file.exists():
        logging.info("Splitting unified index into category files...")
        from collections import defaultdict
        
        chunks_by_category = defaultdict(list)
        with open(unified_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    chunk = json.loads(line)
                    category = chunk.get('metadata', {}).get('nlp_category', 'general')
                    chunks_by_category[category].append(chunk)
        
        for category, chunks in chunks_by_category.items():
            category_file = detail_dir / f"chunks.{category}.jsonl"
            with open(category_file, 'w', encoding='utf-8') as f:
                for chunk in chunks:
                    f.write(json.dumps(chunk, ensure_ascii=False) + '\n')
            logging.info(f"Wrote {len(chunks)} chunks to chunks.{category}.jsonl")
    
    # Update manifest
    manifest["completed"] = now_iso()
    with open(Path(config.OUT_DIR, "manifests", "run_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    
    # Finalize incremental processing
    indexer.finalize_run()

    logging.info(f"Incremental processing complete. Processed {len(files_to_process)} files.")

if __name__ == "__main__":
    main()