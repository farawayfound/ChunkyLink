# -*- coding: utf-8 -*-
"""
Index Size Estimator — fast no-cross-reference build into JSON/temp.
Processes all source files in parallel, applies full NLP enrichment and
quality filtering, then reports chunk counts and sizes by category.
Cross-references, router records, and state tracking are all skipped.

Usage:
    cd indexers
    python scripts/estimate_index_size.py
"""

import json, logging, sys, time
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

# Reuse the same worker function from build_index — identical enrichment pipeline
try:
    from build_index import _process_file
    from utils.text_processing import classify_profile
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from indexers.build_index import _process_file
    from indexers.utils.text_processing import classify_profile

# ── Output dir ────────────────────────────────────────────────────────────────

TEMP_DIR = Path(config.OUT_DIR) / "temp"
TEMP_DETAIL_DIR = TEMP_DIR / "detail"
TEMP_DETAIL_DIR.mkdir(parents=True, exist_ok=True)

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(str(TEMP_DIR / "estimate.log"), encoding="utf-8"),
    ]
)

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    src = Path(config.SRC_DIR)
    files = []
    for ext in ("*.pdf", "*.pptx", "*.docx", "*.txt", "*.csv"):
        files.extend(src.glob(f"**/{ext}"))

    if not files:
        logging.error(f"No source files found in {src}")
        return

    logging.info(f"Estimating index size for {len(files)} files (no cross-references)")

    cfg = {k: getattr(config, k) for k in dir(config) if not k.startswith("_")}
    # Disable OCR for speed — we want chunk counts, not OCR text
    cfg["ENABLE_OCR"] = False

    file_tasks = [
        (path, "auto" if getattr(config, "ENABLE_AUTO_CLASSIFICATION", False) else classify_profile(path.name))
        for path in files
    ]

    ocr_workers  = getattr(config, "PARALLEL_OCR_WORKERS", 4)
    total_cores  = multiprocessing.cpu_count()
    file_workers = getattr(config, "FILE_WORKERS", 0) or max(1, min(8, total_cores // max(1, ocr_workers // 2)))

    logging.info(f"Using {file_workers} parallel workers")

    chunks_by_category = defaultdict(list)
    failed = []
    t0 = time.time()

    with ProcessPoolExecutor(max_workers=file_workers) as executor:
        futures = {
            executor.submit(_process_file, path, prof, cfg): (path, prof)
            for path, prof in file_tasks
        }
        for future in as_completed(futures):
            path, prof = futures[future]
            try:
                result = future.result()
                for chunk in result["detail"]:
                    cat = chunk.get("metadata", {}).get("nlp_category", "general")
                    chunks_by_category[cat].append(chunk)
                logging.info(f"  {path.name}: {len(result['detail'])} chunks")
            except Exception as ex:
                logging.warning(f"  FAILED {path.name}: {ex}")
                failed.append(path.name)

    elapsed = round(time.time() - t0)

    # ── Write temp JSONL files ─────────────────────────────────────────────────
    total_chunks = 0
    total_bytes  = 0
    rows = []

    for cat in sorted(chunks_by_category):
        chunks = chunks_by_category[cat]
        out_file = TEMP_DETAIL_DIR / f"chunks.{cat}.jsonl"
        raw = "\n".join(json.dumps(c, ensure_ascii=False) for c in chunks) + "\n"
        out_file.write_text(raw, encoding="utf-8")
        size_bytes = out_file.stat().st_size
        total_chunks += len(chunks)
        total_bytes  += size_bytes
        rows.append((cat, len(chunks), size_bytes))

    # ── Report ─────────────────────────────────────────────────────────────────
    def fmt_bytes(b):
        return f"{b/1048576:.1f} MB" if b >= 1048576 else f"{b/1024:.1f} KB"

    print()
    print("=" * 60)
    print("  INDEX SIZE ESTIMATE (no cross-references)")
    print("=" * 60)
    print(f"  {'Category':<20} {'Chunks':>8}  {'Size':>10}  {'% of total':>10}")
    print(f"  {'-'*20}  {'-'*8}  {'-'*10}  {'-'*10}")
    for cat, count, size in sorted(rows, key=lambda r: r[1], reverse=True):
        pct = count / total_chunks * 100 if total_chunks else 0
        print(f"  {cat:<20} {count:>8,}  {fmt_bytes(size):>10}  {pct:>9.1f}%")
    print(f"  {'-'*20}  {'-'*8}  {'-'*10}  {'-'*10}")
    print(f"  {'TOTAL':<20} {total_chunks:>8,}  {fmt_bytes(total_bytes):>10}")
    print()
    print(f"  Files processed : {len(files) - len(failed)} / {len(files)}")
    if failed:
        print(f"  Failed          : {', '.join(failed)}")
    print(f"  Elapsed         : {elapsed // 60}m {elapsed % 60}s")
    print(f"  Output          : {TEMP_DETAIL_DIR}")
    print("=" * 60)
    print()

    # Also write a JSON summary for programmatic use
    summary = {
        "total_chunks": total_chunks,
        "total_bytes": total_bytes,
        "by_category": {cat: {"chunks": count, "bytes": size} for cat, count, size in rows},
        "files_processed": len(files) - len(failed),
        "files_failed": failed,
        "elapsed_s": elapsed,
    }
    (TEMP_DIR / "estimate_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logging.info("Summary written to JSON/temp/estimate_summary.json")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    multiprocessing.set_start_method("spawn", force=True)
    main()
