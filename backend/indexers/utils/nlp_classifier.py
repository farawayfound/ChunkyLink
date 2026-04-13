# -*- coding: utf-8 -*-
"""NLP-based content classification and tagging for ChunkyPotato.

Uses a hybrid Ollama + spaCy pipeline:
  1. Per-document: Ollama generates dynamic content categories from a text sample.
  2. Per-chunk: spaCy assigns each chunk to the best-fitting category via keyword
     and noun-chunk overlap (no LLM call per chunk).
"""
import asyncio
import json
import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    import spacy
    from spacy.matcher import PhraseMatcher
    nlp = spacy.load("en_core_web_md")
    _HAS_SPACY = True
except (ImportError, OSError):
    nlp = None
    PhraseMatcher = None
    _HAS_SPACY = False
    logging.warning(
        "nlp_classifier: spaCy/en_core_web_md unavailable — "
        "NLP classification disabled. Run: pip install spacy && python -m spacy download en_core_web_md"
    )


_GENERAL_CATEGORY = [{"name": "general", "description": "general content", "keywords": []}]

_CATEGORY_SYSTEM_PROMPT = (
    "You analyze documents and identify distinct content categories. "
    "Return ONLY a JSON array — no markdown fences, no commentary.\n"
    "Each element: {\"name\": \"short-kebab-label\", "
    "\"description\": \"one sentence about what this category covers\", "
    "\"keywords\": [\"key\", \"terms\", \"that\", \"signal\", \"this\", \"category\"]}\n"
    "Rules:\n"
    "- Produce 3 to 7 categories.\n"
    "- Names must be lowercase kebab-case, max 3 words (e.g. 'project-management').\n"
    "- Keywords should be concrete terms found in the text, not abstract labels.\n"
    "- Categories must reflect THIS document's actual content, not generic resume sections."
)


def _build_matchers(content_tags: dict) -> dict:
    if not _HAS_SPACY:
        return {}
    matchers = {}
    for tag, keywords in content_tags.items():
        matcher = PhraseMatcher(nlp.vocab, attr="LOWER")
        patterns = [nlp.make_doc(kw) for kw in keywords]
        matcher.add(tag, patterns)
        matchers[tag] = matcher
    return matchers


def _get_config():
    from backend.config import get_settings
    return get_settings()


# ---------------------------------------------------------------------------
# Phase 1 — Document-level category generation (Ollama)
# ---------------------------------------------------------------------------

def _categories_cache_path(index_dir: Path, doc_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", doc_id)
    cache_dir = index_dir / "detail"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"categories.{safe}.json"


def load_cached_categories(index_dir: Path, doc_id: str) -> Optional[List[Dict]]:
    path = _categories_cache_path(index_dir, doc_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list) and data:
            return data
    except Exception:
        pass
    return None


def _save_categories_cache(index_dir: Path, doc_id: str, categories: List[Dict]) -> None:
    path = _categories_cache_path(index_dir, doc_id)
    try:
        path.write_text(json.dumps(categories, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        logging.warning("nlp_classifier: failed to cache categories for %s: %s", doc_id, exc)


def _parse_category_json(raw: str) -> Optional[List[Dict]]:
    """Best-effort extraction of the JSON array from an LLM response."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        raw = raw.strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if not m:
            return None
        try:
            parsed = json.loads(m.group())
        except json.JSONDecodeError:
            return None

    if not isinstance(parsed, list) or not parsed:
        return None

    cleaned: List[Dict] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip().lower()
        name = re.sub(r"[^a-z0-9-]", "-", name).strip("-")[:40]
        if not name:
            continue
        cleaned.append({
            "name": name,
            "description": str(item.get("description", "")),
            "keywords": [str(k).lower() for k in (item.get("keywords") or []) if k],
        })
    return cleaned if cleaned else None


async def generate_document_categories(
    text_sample: str,
    doc_id: str,
    index_dir: Optional[Path] = None,
    force: bool = False,
) -> List[Dict]:
    """Ask Ollama to identify content categories for a document.

    Returns a list of ``{"name", "description", "keywords"}`` dicts.
    Falls back to ``[{"name": "general", ...}]`` on any failure.
    """
    if index_dir and not force:
        cached = load_cached_categories(index_dir, doc_id)
        if cached:
            return cached

    if not text_sample.strip():
        return list(_GENERAL_CATEGORY)

    try:
        from backend.chat.ollama_client import generate

        prompt = (
            f"Document: {doc_id}\n\n"
            f"--- BEGIN EXCERPT (first ~4000 chars) ---\n"
            f"{text_sample[:4000]}\n"
            f"--- END EXCERPT ---\n\n"
            "Identify 3-7 content categories for this document."
        )
        raw = await generate(
            prompt=prompt,
            system=_CATEGORY_SYSTEM_PROMPT,
            temperature=0.15,
            max_tokens=600,
        )
        categories = _parse_category_json(raw)
        if categories:
            if index_dir:
                _save_categories_cache(index_dir, doc_id, categories)
            return categories
        logging.warning("nlp_classifier: Ollama returned unparseable categories for %s", doc_id)
    except Exception as exc:
        logging.warning("nlp_classifier: Ollama category generation failed for %s: %s", doc_id, exc)

    return list(_GENERAL_CATEGORY)


def generate_document_categories_sync(
    text_sample: str,
    doc_id: str,
    index_dir: Optional[Path] = None,
    force: bool = False,
) -> List[Dict]:
    """Sync wrapper for ``generate_document_categories``."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        new_loop = asyncio.new_event_loop()
        try:
            return new_loop.run_until_complete(
                generate_document_categories(text_sample, doc_id, index_dir, force)
            )
        finally:
            new_loop.close()
    return asyncio.run(
        generate_document_categories(text_sample, doc_id, index_dir, force)
    )


# ---------------------------------------------------------------------------
# Phase 2 — Chunk-level classification (spaCy against dynamic categories)
# ---------------------------------------------------------------------------

def classify_chunk_against_categories(
    doc,
    categories: List[Dict],
    entities: Dict[str, list],
    noun_chunks: List[str],
) -> str:
    """Score a spaCy doc against each document-level category and return the best match."""
    if not categories or len(categories) == 1:
        return categories[0]["name"] if categories else "general"

    text_lower = doc.text.lower()
    best_name = categories[0]["name"]
    best_score = -1.0

    for cat in categories:
        score = 0.0
        for kw in cat.get("keywords", []):
            kw_lower = kw.lower()
            score += text_lower.count(kw_lower) * 2

        desc_words = set(cat.get("description", "").lower().split())
        for nc in noun_chunks:
            overlap = len(desc_words & set(nc.split()))
            score += overlap * 1.5

        for kw in cat.get("keywords", []):
            kw_lower = kw.lower()
            for ent_values in entities.values():
                for val in (ent_values if isinstance(ent_values, list) else []):
                    if kw_lower in val.lower():
                        score += 3

        if score > best_score:
            best_score = score
            best_name = cat["name"]

    return best_name


# ---------------------------------------------------------------------------
# Core NLP extraction (entities, tags, phrases) + classification entry point
# ---------------------------------------------------------------------------

def classify_content_nlp(
    text: str,
    max_chars: int = 5000,
    auto_classify: bool = True,
    auto_tag: bool = True,
    categories: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    if not _HAS_SPACY:
        return {"category": "general", "tags": [], "entities": {}, "key_phrases": []}
    settings = _get_config()
    doc = nlp(text[:max_chars])

    entities = {}
    for ent in doc.ents:
        entities.setdefault(ent.label_, set()).add(ent.text)
    entities = {k: list(v)[:10] for k, v in entities.items()}

    noun_chunks = [chunk.text.lower() for chunk in doc.noun_chunks if len(chunk.text) > 3][:20]

    if auto_tag:
        tags = _generate_automatic_tags(doc, entities, noun_chunks)
    else:
        matchers = _build_matchers(settings.CONTENT_TAGS)
        tags = set()
        for tag, matcher in matchers.items():
            if matcher(doc):
                tags.add(tag)

    tags = list(tags)[:settings.MAX_TAGS_PER_CHUNK]

    if auto_classify and categories:
        category = classify_chunk_against_categories(doc, categories, entities, noun_chunks)
    elif auto_classify:
        category = "general"
    else:
        category = "general"

    return {
        "category": category,
        "tags": tags,
        "entities": entities,
        "key_phrases": noun_chunks,
    }


def _normalize_tag(tag: str) -> str:
    tag = tag.lower().strip()
    tag = re.sub(r'[\n\r]+', ' ', tag)
    tag = re.sub(r'\s+', '-', tag)
    tag = re.sub(r'[^\w\-]', '', tag)
    tag = re.sub(r'\-{2,}', '-', tag)
    tag = tag.strip('-')
    return tag[:50]


def _generate_automatic_tags(doc, entities: Dict, noun_chunks: List[str]) -> set:
    tags = set()
    exclusions = {"thing", "way", "use", "make", "get", "go", "come", "take", "give",
                  "know", "think", "see", "want", "look", "need", "try", "work", "call"}

    acronym_freq = {}
    for token in doc:
        if token.text.isupper() and 2 <= len(token.text) <= 7 and token.is_alpha:
            acronym_freq[token.text] = acronym_freq.get(token.text, 0) + 1
    for acronym, freq in acronym_freq.items():
        if freq >= 2:
            tags.add(acronym)

    noun_freq = {}
    for token in doc:
        if (token.pos_ in ["NOUN", "PROPN"] and not token.is_stop
                and len(token.text) >= 4 and token.lemma_.lower() not in exclusions):
            noun_freq[token.lemma_.lower()] = noun_freq.get(token.lemma_.lower(), 0) + 1
    for noun, freq in sorted(noun_freq.items(), key=lambda x: x[1], reverse=True)[:5]:
        if freq >= 2:
            tags.add(noun)

    for org in entities.get("ORG", [])[:3]:
        if len(org) < 30:
            tags.add(_normalize_tag(org))
    for product in entities.get("PRODUCT", [])[:3]:
        if len(product) < 30:
            tags.add(_normalize_tag(product))

    verb_freq = {}
    for token in doc:
        if (token.pos_ == "VERB" and not token.is_stop
                and len(token.text) >= 4 and token.lemma_.lower() not in exclusions):
            verb_freq[token.lemma_.lower()] = verb_freq.get(token.lemma_.lower(), 0) + 1
    for verb, freq in sorted(verb_freq.items(), key=lambda x: x[1], reverse=True)[:3]:
        if freq >= 2:
            tags.add(f"action-{verb}")

    return {_normalize_tag(t) for t in tags if len(_normalize_tag(t)) >= 3}


def enrich_record_with_nlp(
    record: Dict,
    text_sample: str,
    auto_classify: bool = None,
    auto_tag: bool = None,
    categories: Optional[List[Dict]] = None,
) -> Dict:
    """Enrich a chunk record with NLP-derived metadata.

    *categories* is the per-document list produced by
    ``generate_document_categories``.  When provided (and auto-classify is
    on), chunk classification uses the dynamic category list instead of a
    static heuristic.
    """
    try:
        settings = _get_config()
        if auto_classify is None:
            auto_classify = settings.ENABLE_AUTO_CLASSIFICATION
        if auto_tag is None:
            auto_tag = settings.ENABLE_AUTO_TAGGING

        nlp_data = classify_content_nlp(
            text_sample,
            auto_classify=auto_classify,
            auto_tag=auto_tag,
            categories=categories,
        )

        if "metadata" in record:
            record["metadata"]["nlp_category"] = nlp_data["category"]
            record["metadata"]["nlp_entities"] = nlp_data["entities"]
            record["metadata"]["key_phrases"] = nlp_data["key_phrases"]

        if auto_tag:
            record["tags"] = nlp_data["tags"]
        else:
            existing_tags = set(record.get("tags", []))
            existing_tags.update(nlp_data["tags"])
            record["tags"] = list(existing_tags)

        matchers = _build_matchers(settings.CONTENT_TAGS)
        if matchers:
            doc = nlp(text_sample[:5000])
            domain_tags = set(record.get("tags", []))
            for tag, matcher in matchers.items():
                if matcher(doc):
                    domain_tags.add(tag)
            record["tags"] = list(domain_tags)

        if auto_classify and "tags" in record:
            record["tags"] = [nlp_data["category"]] + [t for t in record["tags"] if t != nlp_data["category"]]
        record["tags"] = record["tags"][:settings.MAX_TAGS_PER_CHUNK]

    except Exception as e:
        logging.warning(f"NLP enrichment failed: {e}")

    return record
