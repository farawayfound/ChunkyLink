# -*- coding: utf-8 -*-
"""
vpoRAG Indexer Config — server instance (Linux paths)
Generated for /srv/vpo_rag on Ubuntu 24.04
"""

SRC_DIR = "/srv/vpo_rag/source_docs"
OUT_DIR = "/srv/vpo_rag/JSON"

PARA_TARGET_TOKENS = 512
PARA_OVERLAP_TOKENS = 128
MIN_CHUNK_TOKENS = 16
MAX_ROUTER_SUMMARY_CHARS = 3000
MAX_HIERARCHY_DEPTH = 6

DEDUPLICATION_INTENSITY = 1
ENABLE_CROSS_FILE_DEDUP = False

MAX_RELATED_CHUNKS = 5
MIN_SIMILARITY_THRESHOLD = 0.65
ENABLE_CROSS_REFERENCES = True
TERM_ALIASES = {}

# Tags excluded from Phase 2 discovery and Phase 4 scoring during search.
# NLP artifacts that appear in nearly every chunk and produce false signals.
TAG_STOPLIST = {
    "vpo", "post", "address", "report", "communications", "client",
    "lob", "functiona", "functiona-client", "clos", "issue", "spectrum",
    "action-provide", "action-select", "action-enter", "action-configure",
    "action-check", "action-verify", "action-review", "action-update",
    "select", "select-research", "your", "home", "experience", "usage",
    "task", "escalations-usage-task", "role", "mso", "pid",
}

ENABLE_CAMELOT = False
ENABLE_OCR = True
OCR_MIN_IMAGE_SIZE = (150, 150)
OCR_LANGUAGES = 'eng'
PARALLEL_OCR_WORKERS = 4   # Tesseract workers per file
FILE_WORKERS = 0            # 0 = auto (total_cores // (OCR_WORKERS/2)); set explicitly to override
TESSERACT_PATH = None  # auto-detect on Linux

CHUNK_QUALITY_MIN_WORDS = 10
ENABLE_AUTO_CLASSIFICATION = True
ENABLE_AUTO_TAGGING = True
MAX_TAGS_PER_CHUNK = 25

DOC_PROFILES = {
    "glossary": ["glossary", "acronym"],
    "slides": [".pptx"],
    "manual": ["vertical playbooks", "playbook"],
    "sop": ["creating tickets", "cross vertical"],
    "queries": ["splunk", "kibana", "queries"],
    "reference": ["reference", "guide"],
}

CONTENT_TAGS = {
    "splunk": ["splunk", "index=", "sourcetype="],
    "kibana": ["kibana", "elasticsearch"],
    "troubleshooting": ["troubleshoot", "error", "issue", "problem", "fix"],
    "procedures": ["procedure", "step", "process", "workflow"],
    "queries": ["query", "search", "filter"],
    "tickets": ["ticket", "jira", "incident"],
    "high-split": ["high split", "hsc", "high-split"],
    "cpe": ["cpe", "customer premise", "equipment"],
    "entitlements": ["entitlement", "ace", "clm"],
}
