# -*- coding: utf-8 -*-
"""
Automatic CSV watcher — monitors DPSTRIAGE and POSTRCA drop folders.

On each new CSV:
  1. Validate required columns + at least one data row
  2. If invalid  → move to <folder>/invalid/
  3. If valid    → run ingest script, then archive all older CSVs to <folder>/archive/

Run as a systemd service (vporag-csv-sync.service).
"""
import csv, logging, shutil, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    from logger import log_csv_ingest
except Exception:
    log_csv_ingest = lambda *a, **kw: None

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    raise SystemExit("pip install watchdog")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
try:
    import config
except ImportError:
    raise SystemExit("config.py not found — copy config.example.py to config.py")

DPSTRIAGE_DIR = Path(getattr(config, "DPSTRIAGE_CSV_DIR", "/srv/samba/share/dpstriageCSV"))
POSTRCA_DIR   = Path(getattr(config, "POSTRCA_CSV_DIR",   "/srv/samba/share/postrcaCSV"))
PYTHON        = getattr(config, "PYTHON_BIN",             "/srv/vpo_rag/venv/bin/python")
LOG_FILE      = getattr(config, "CSV_WATCHER_LOG",        "/srv/samba/share/csv_watcher.log")

SCRIPTS_DIR = Path(__file__).parent

INGEST_SCRIPTS = {
    DPSTRIAGE_DIR: SCRIPTS_DIR / "ingest_jira_csv.py",
    POSTRCA_DIR:   SCRIPTS_DIR / "ingest_postrca_csv.py",
}

# Required columns that must be present in the CSV header
REQUIRED_COLUMNS = {"Issue key", "Status", "Summary", "Created", "Updated"}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate_csv(path: Path) -> tuple[bool, str]:
    """Return (is_valid, reason). Checks encoding, required columns, and row count."""
    try:
        with open(path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            headers = set(reader.fieldnames or [])
            missing = REQUIRED_COLUMNS - headers
            if missing:
                return False, f"Missing required columns: {missing}"
            rows = 0
            for _ in reader:
                rows += 1
                if rows >= 1:
                    break
            if rows == 0:
                return False, "CSV has no data rows"
        return True, "ok"
    except UnicodeDecodeError as e:
        return False, f"Encoding error: {e}"
    except Exception as e:
        return False, f"Parse error: {e}"

# ---------------------------------------------------------------------------
# File management
# ---------------------------------------------------------------------------
def _ensure_dirs(watch_dir: Path):
    (watch_dir / "archive").mkdir(exist_ok=True)
    (watch_dir / "invalid").mkdir(exist_ok=True)

def archive_older_csvs(watch_dir: Path, keep: Path):
    """Move all CSVs in watch_dir except `keep` into archive/, timestamped."""
    archive_dir = watch_dir / "archive"
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    for f in watch_dir.glob("*.csv"):
        if f == keep:
            continue
        dest = archive_dir / f"{f.stem}_{ts}{f.suffix}"
        shutil.move(str(f), str(dest))
        log.info(f"Archived {f.name} → archive/{dest.name}")

def move_to_invalid(path: Path, reason: str):
    invalid_dir = path.parent / "invalid"
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest = invalid_dir / f"{path.stem}_{ts}{path.suffix}"
    shutil.move(str(path), str(dest))
    log.warning(f"Invalid CSV moved → invalid/{dest.name} | Reason: {reason}")

# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------
def run_ingest(watch_dir: Path, csv_path: Path):
    script = INGEST_SCRIPTS[watch_dir]
    log.info(f"Running ingest: {script.name} for {csv_path.name}")
    result = subprocess.run(
        [PYTHON, str(script)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        log.error(f"Ingest failed (rc={result.returncode}):\n{result.stderr.strip()}")
        # log_csv_ingest is called by the ingest script itself on success/fail with real row counts
        return False
    log.info(f"Ingest succeeded: {result.stdout.strip()}")
    return True

# ---------------------------------------------------------------------------
# Event handler
# ---------------------------------------------------------------------------
class CSVDropHandler(FileSystemEventHandler):
    def __init__(self, watch_dir: Path):
        self.watch_dir = watch_dir
        self._seen: set[str] = set()  # dedup guard — prevents on_created + on_closed both firing
        _ensure_dirs(watch_dir)

    def on_closed(self, event):
        """Triggered when a file write is fully closed (watchdog >= 2.1 on Linux).
        Primary handler -- on_created is suppressed when this fires.
        """
        if event.src_path in self._seen:
            return
        self._seen.add(event.src_path)
        self._handle(event.src_path)

    def on_created(self, event):
        """Fallback for systems where on_closed is not fired (e.g. NFS/Samba mounts)."""
        if event.src_path in self._seen:
            return
        self._seen.add(event.src_path)
        time.sleep(1)  # ensure file is fully written before reading
        self._handle(event.src_path)

    def _handle(self, src_path: str):
        path = Path(src_path)
        if path.suffix.lower() != ".csv":
            return
        # Ignore files already in archive/ or invalid/ subfolders
        if path.parent != self.watch_dir:
            return

        log.info(f"Detected new file: {path.name} in {self.watch_dir.name}")

        valid, reason = validate_csv(path)
        if not valid:
            move_to_invalid(path, reason)
            return

        success = run_ingest(self.watch_dir, path)
        if success:
            archive_older_csvs(self.watch_dir, keep=path)
        else:
            # Ingest failed — treat as invalid so it doesn't loop
            move_to_invalid(path, "Ingest script returned non-zero exit code")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    observer = Observer()
    for watch_dir in (DPSTRIAGE_DIR, POSTRCA_DIR):
        if not watch_dir.exists():
            log.warning(f"Watch directory does not exist, skipping: {watch_dir}")
            continue
        handler = CSVDropHandler(watch_dir)
        observer.schedule(handler, str(watch_dir), recursive=False)
        log.info(f"Watching: {watch_dir}")

    observer.start()
    log.info("CSV watcher started.")
    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()
        log.info("CSV watcher stopped.")

if __name__ == "__main__":
    main()
