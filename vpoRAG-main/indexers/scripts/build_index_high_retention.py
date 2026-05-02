# -*- coding: utf-8 -*-
"""
High Knowledge Retention VPO RAG Indexer
- Maximizes knowledge capture with minimal loss
- Includes QA validation and reporting
"""

import logging, sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from core.incremental_indexer import IncrementalIndexer
from utils.topic_metadata import add_topic_metadata
from utils.text_processing import classify_profile
from utils.nlp_classifier import enrich_record_with_nlp
from processors.pdf_processor import build_for_pdf
from utils.quality_assurance import validate_extraction_completeness, generate_qa_report

def main():
    
    # Setup directories and logging
    out_dir = Path(config.OUT_DIR)
    for p in [out_dir / "detail", out_dir / "router", out_dir / "logs", out_dir / "state"]:
        p.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        filename=str(out_dir / "logs" / "high_retention.log"),
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )
    
    # Initialize indexer
    indexer = IncrementalIndexer(config.OUT_DIR)
    files_by_status = indexer.get_files_to_process(config.SRC_DIR)
    files_to_process = files_by_status["new"] + files_by_status["modified"]
    
    if not files_to_process:
        logging.info("No files to process")
        return
    
    all_router_docs, all_router_chapters, all_detail = [], [], []
    qa_results = []
    
    for path in files_to_process:
        if path in files_by_status["modified"]:
            old_doc_ids = indexer.get_existing_doc_ids(path)
            if old_doc_ids:
                indexer.remove_old_records(old_doc_ids)
        
        prof = classify_profile(path.name)
        logging.info(f"Processing [{prof}] {path}")
        
        if path.suffix.lower() == ".pdf":
            try:
                res = build_for_pdf(path, vars(config))
                full_text = " ".join([r["summary"] for r in res["router"]])[:5000]
                
                # Add topic metadata with NLP enrichment
                for record in res["router"]:
                    all_router_chapters.append(enrich_record_with_nlp(add_topic_metadata(record, path), record.get("summary", "")))
                
                doc_record = {
                    "route_id": f"{path.name}::doc",
                    "title": path.stem,
                    "scope_pages": [1, res["pages"]],
                    "summary": full_text[:config.MAX_ROUTER_SUMMARY_CHARS],
                    "tags": [prof]
                }
                all_router_docs.append(enrich_record_with_nlp(add_topic_metadata(doc_record, path), full_text))
                
                for record in res["detail"]:
                    all_detail.append(enrich_record_with_nlp(add_topic_metadata(record, path), record.get("text_raw", record.get("text", ""))))
                
                # QA validation
                qa_result = validate_extraction_completeness(path, res["detail"])
                qa_results.append(qa_result)
                
                indexer.mark_processed(path, [path.name])
                
            except Exception as ex:
                logging.exception(f"Error processing {path.name}: {ex}")
    
    # Save records
    new_records = {
        "router_docs": all_router_docs,
        "router_chapters": all_router_chapters,
        "detail": all_detail
    }
    indexer.append_new_records(new_records)
    indexer.finalize_run()
    
    # Generate QA report
    generate_qa_report(qa_results, out_dir)
    
    logging.info(f"High-retention processing complete. Processed {len(files_to_process)} files.")

if __name__ == "__main__":
    main()