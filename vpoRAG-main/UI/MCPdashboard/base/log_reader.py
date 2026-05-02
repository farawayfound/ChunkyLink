# -*- coding: utf-8 -*-
"""Abstract LogReader — defines the interface all log reader implementations must satisfy."""
from abc import ABC, abstractmethod


class LogReader(ABC):
    """Encapsulates log access strategy (SSH vs local file)."""

    @abstractmethod
    def fetch_lines(self, max_lines: int = 5000) -> list[str]:
        """Return up to max_lines non-empty lines from mcp_access.log."""

    @abstractmethod
    def check_server_status(self) -> dict:
        """Return {'active': bool, 'status': str}."""

    @abstractmethod
    def read_learned_chunks(self) -> list[str]:
        """Return raw JSONL lines from chunks.learned.jsonl."""

    @abstractmethod
    def run_git_log(self) -> str:
        """Return stdout of: git log --format='%H|%ai|%s' -- chunks.learned.jsonl"""

    @abstractmethod
    def run_git_show(self, commit: str) -> str:
        """Return stdout of: git show --unified=0 <commit> -- chunks.learned.jsonl"""

    @abstractmethod
    def run_git_show_file(self, commit: str) -> str:
        """Return the full file contents of chunks.learned.jsonl at <commit>."""

    @abstractmethod
    def run_git_op(self, args: list[str]) -> dict:
        """Run a git command in the detail dir. Return {'ok': bool, 'output': str}."""

    @abstractmethod
    def restore_learned_to_commit(self, action: str, commit: str) -> dict:
        """Safely restore chunks.learned.jsonl to a prior state without git revert.

        action values:
          rollback_to    — restore file to exact content at <commit>, commit result
          remove_single  — restore file to content at parent of <commit>, commit result
          forward_to_latest — restore file to current HEAD content, commit result

        Never uses git revert — writes file content directly to avoid conflict markers.
        Returns {'ok': bool, 'output': str}.
        """

    @abstractmethod
    def read_index_files(self) -> list[dict]:
        """Return a list of dicts with keys: name, size_bytes, line_count for each
        chunks.*.jsonl file in the detail directory (excluding chunks.jsonl unified)."""

    @abstractmethod
    def list_source_files(self) -> list[dict]:
        """Return list of dicts with keys: name, size_bytes, modified_ts for each file
        in the source_docs directory."""

    @abstractmethod
    def delete_source_file(self, filename: str) -> dict:
        """Delete a file from source_docs. Return {'ok': bool, 'output': str}."""

    @abstractmethod
    def upload_source_file(self, filename: str, data: bytes) -> dict:
        """Write data to source_docs/<filename>. Return {'ok': bool, 'output': str}."""

    @abstractmethod
    def kill_build(self) -> dict:
        """Kill the running build process. Return {'ok': bool, 'output': str}."""

    @abstractmethod
    def trigger_build(self, force_full: bool, user_id: str) -> dict:
        """Trigger a KB index rebuild. Return {'ok': bool, 'output': str}."""

    @abstractmethod
    def get_build_status(self) -> dict:
        """Return live build status from /tmp/dashboard_build.log and /proc.
        Keys: running, pid, start_time, elapsed_s, cpu_pct, rss_mb,
              files_processed, files_total, current_file, force_full,
              user_id, trigger, log_lines."""

    @abstractmethod
    def list_csv_files(self) -> dict:
        """Return {'dpstriage': [...], 'postrca': [...]} — each entry has name, size_bytes,
        modified_ts. Lists the active CSV dir (not archive)."""

    @abstractmethod
    def upload_csv_file(self, table: str, filename: str, data: bytes) -> dict:
        """Write data to the correct Samba CSV dir and trigger the ingest script.
        table: 'dpstriage' | 'postrca'. Return {'ok': bool, 'output': str, 'ingest': dict}."""

    @abstractmethod
    def download_source_file(self, filename: str) -> tuple[bytes, str]:
        """Return (file_bytes, mime_type) for a file in source_docs. Raise FileNotFoundError if missing."""

    @abstractmethod
    def download_csv_file(self, table: str, filename: str) -> bytes:
        """Return raw bytes of a CSV file from the correct Samba dir. Raise FileNotFoundError if missing."""

    @abstractmethod
    def download_jira_db(self, table) -> tuple[bytes, str]:
        """Dump both Jira MySQL tables into a SQLite .db and return (bytes, filename)."""

    @abstractmethod
    def download_index_zip(self) -> bytes:
        """Return a zip archive of all chunks.*.jsonl files from the detail directory."""

    @abstractmethod
    def delete_learned_chunk(self, chunk_id: str, user_id: str) -> dict:
        """Remove a chunk by ID from chunks.learned.jsonl and commit. Return {'ok': bool, 'output': str}."""

    @abstractmethod
    def write_learned_chunk_edit(self, chunk_id: str, new_text: str,
                                  new_tags: list, new_title: str, user_id: str) -> dict:
        """Edit a learned chunk in-place by ID. Return {'ok': bool, 'commit': str}."""
