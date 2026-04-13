# -*- coding: utf-8 -*-
"""Topic metadata utilities for document classification."""
from pathlib import Path
from typing import Dict


def add_topic_metadata(record: Dict, file_path: Path) -> Dict:
    if "metadata" in record:
        record["metadata"]["file_path"] = str(file_path)

    if "tags" not in record:
        record["tags"] = []

    return record
