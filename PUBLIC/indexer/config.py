#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Configuration for NovaRAG Indexer."""

from typing import Dict, List, Set

# Generic category keywords (no domain-specific terms)
CATEGORY_KEYWORDS = {
    "technical": [
        "api", "endpoint", "request", "response", "method", "post", "get",
        "database", "query", "table", "column", "schema", "index",
        "server", "client", "socket", "websocket", "http", "https",
        "json", "xml", "yaml", "configuration", "config"
    ],
    "business": [
        "policy", "procedure", "guideline", "process", "workflow",
        "approval", "budget", "expense", "revenue", "profit",
        "customer", "client", "vendor", "supplier", "contract"
    ],
    "hr": [
        "employee", "hire", "terminate", "salary", "benefit", "leave",
        "vacation", "sick", "performance", "review", "promotion",
        "training", "development", "onboard", "offboard"
    ],
    "legal": [
        "contract", "agreement", "liability", "indemnify", "confidential",
        "patent", "trademark", "copyright", "compliance", "regulation",
        "audit", "report", "evidence", "exhibit", "appendix"
    ],
    "finance": [
        "invoice", "payment", "refund", "deposit", "withdrawal",
        "balance", "transaction", "ledger", "accounting", "tax",
        "expense", "revenue", "profit", "loss", "budget"
    ],
    "sales": [
        "quote", "proposal", "contract", "order", "shipment",
        "delivery", "return", "exchange", "warranty", "support",
        "discount", "promotion", "campaign", "lead", "conversion"
    ],
    "general": [
        "information", "update", "notice", "announcement",
        "meeting", "schedule", "calendar", "contact", "directory"
    ]
}

# Generic PII patterns (no CPNI-specific)
PII_PATTERNS = {
    "ssn": r'\b\d{3}-\d{2}-\d{4}\b',
    "credit_card": r'\b(?:\d{4}[- ]?){3}\d{4}\b',
    "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    "phone": r'\b(?:\+1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b',
    "date": r'\b\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}\b',
}

# File type configurations
FILE_PROCESSORS = {
    ".pdf": "PDFProcessor",
    ".txt": "TextProcessor", 
    ".csv": "CSVProcessor"
}

# Chunking configuration
CHUNK_CONFIG = {
    "max_chunk_size": 500,       # characters
    "overlap_size": 50,          # characters
    "min_chunk_size": 50         # characters
}

# Index output structure
INDEX_STRUCTURE = {
    "detail": "detailed_document_data.jsonl",
    "router": "cross_reference_index.json", 
    "state": "build_state.json",
    "logs": "build_logs.txt"
}

# Default configuration object
INDEXER_CONFIG: Dict = {
    "chunk_size": 500,
    "overlap": 50,
    "category_keywords": CATEGORY_KEYWORDS,
    "pii_patterns": PII_PATTERNS,
    "file_processors": FILE_PROCESSORS,
    "index_structure": INDEX_STRUCTURE,
    "allowed_extensions": {".pdf", ".txt", ".csv"},
}

# Generic terms (no VPO-specific)
TERM_ALIASES: Dict[str, List[str]] = {
    "document": ["doc", "paper", "file"],
    "search": ["query", "lookup", "find"],
}