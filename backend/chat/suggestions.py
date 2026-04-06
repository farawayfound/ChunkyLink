# -*- coding: utf-8 -*-
"""Generate suggested questions from indexed chunks using a larger LLM,
then validate each question against the knowledge index."""
import json
import logging
from pathlib import Path

from backend.config import get_settings
from backend.chat.ollama_client import generate
from backend.search.search_kb import search as kb_search

logger = logging.getLogger(__name__)

_SUGGESTION_PROMPT = """\
You are analyzing resume and portfolio content that has been chunked and indexed.
Below are representative text chunks from this person's documents.

Your task: generate exactly 20 high-quality suggested questions that a recruiter
or hiring manager might ask about this person. The questions should be specific
and grounded in the actual content.

CRITICAL RULES:
- Employers/companies are places the person WORKED AT (e.g. "Google", "Acme Corp")
- Skills/tools are technologies or methodologies the person USED (e.g. "Python", "Kubernetes", "Log Analysis")
- Roles/titles are positions the person HELD (e.g. "Senior Engineer", "Team Lead")
- NEVER confuse these categories. Do NOT say "work at Python" or "experience with Google" as an employer.
- Questions about employers should ask about roles, accomplishments, or projects there.
- Questions about skills should ask about proficiency, usage, or projects involving them.
- Mix question types: career narrative, technical depth, project-specific, leadership, etc.

CHUNKS:
{chunks}

Return ONLY a JSON array of 20 question strings, no other text. Example format:
["Question 1?", "Question 2?", ...]"""


def _sample_chunks(chunks_file: Path, max_chunks: int = 30, max_chars: int = 8000) -> str:
    """Read and sample chunks for the prompt, staying within token budget."""
    chunks = []
    with open(chunks_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    chunks.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    if not chunks:
        return ""

    # Prioritize diverse categories
    by_cat: dict[str, list] = {}
    for c in chunks:
        cat = c.get("metadata", {}).get("nlp_category", "general")
        by_cat.setdefault(cat, []).append(c)

    selected = []
    # Round-robin across categories
    while len(selected) < max_chunks and any(by_cat.values()):
        for cat in list(by_cat.keys()):
            if by_cat[cat] and len(selected) < max_chunks:
                selected.append(by_cat[cat].pop(0))
            if not by_cat[cat]:
                del by_cat[cat]

    # Format chunks as text summaries
    parts = []
    total = 0
    for c in selected:
        text = c.get("text", "").strip()
        meta = c.get("metadata", {})
        cat = meta.get("nlp_category", "")
        entities = meta.get("nlp_entities", {})

        summary = f"[Category: {cat}]"
        if entities.get("ORG"):
            summary += f" [Orgs: {', '.join(entities['ORG'][:3])}]"
        if entities.get("PRODUCT"):
            summary += f" [Products: {', '.join(entities['PRODUCT'][:3])}]"
        summary += f"\n{text[:400]}"

        if total + len(summary) > max_chars:
            break
        parts.append(summary)
        total += len(summary)

    return "\n---\n".join(parts)


def _extract_terms(query: str) -> list[str]:
    """Extract search terms from a question for validation."""
    import re
    stop = {
        "what", "is", "are", "how", "do", "does", "can", "could", "would",
        "the", "a", "an", "in", "on", "at", "to", "for", "of", "with",
        "and", "or", "but", "not", "this", "that", "my", "your", "about",
        "from", "by", "as", "it", "me", "you", "we", "they", "i", "be",
        "tell", "describe", "explain", "share", "walk", "through",
    }
    words = re.findall(r'[a-zA-Z0-9][\w\-]*', query.lower())
    terms = [w for w in words if w not in stop and len(w) >= 2]
    return terms or words[:5]


async def _validate_question(question: str, kb_dir: Path, threshold: float = 20.0) -> bool:
    """Check if a question retrieves relevant results from the KB index."""
    terms = _extract_terms(question)
    if not terms:
        return False
    try:
        results = await kb_search(
            terms=terms,
            query=question,
            level="Quick",
            kb_dir=kb_dir,
            max_results=3,
        )
        hits = results.get("results", [])
        if not hits:
            return False
        top_score = hits[0].get("RelevanceScore", 0)
        return top_score >= threshold
    except Exception as e:
        logger.warning(f"suggestions: validation search failed for '{question[:50]}': {e}")
        return False


async def generate_suggestions(kb_dir: Path, progress_cb=None) -> list[str]:
    """Use a larger LLM to generate contextually accurate suggested questions,
    then validate each against the index to ensure they retrieve relevant results.

    Args:
        kb_dir: Path to the knowledge base index directory.
        progress_cb: Optional callback(step, detail) for progress reporting.
    """
    settings = get_settings()
    chunks_file = kb_dir / "detail" / "chunks.jsonl"

    if not chunks_file.exists():
        return []

    chunk_text = _sample_chunks(chunks_file)
    if not chunk_text:
        return []

    # Step 1: Generate candidate questions
    if progress_cb:
        progress_cb("generating", "Generating candidate questions with LLM")

    prompt = _SUGGESTION_PROMPT.format(chunks=chunk_text)

    try:
        response = await generate(
            prompt=prompt,
            system="You are a helpful assistant that generates interview questions. Return only valid JSON.",
            model=settings.SUGGESTION_MODEL,
            temperature=0.7,
            max_tokens=2048,
        )

        response = response.strip()
        if response.startswith("```"):
            response = response.split("\n", 1)[1] if "\n" in response else response
            response = response.rsplit("```", 1)[0].strip()

        candidates = json.loads(response)
        if not isinstance(candidates, list) or not all(isinstance(q, str) for q in candidates):
            logger.warning("suggestions: LLM returned non-list response")
            return []
        candidates = candidates[:20]
    except json.JSONDecodeError:
        logger.warning("suggestions: failed to parse LLM response as JSON")
        return []
    except Exception as e:
        logger.warning(f"suggestions: LLM generation failed: {e}")
        return []

    # Step 2: Validate each question against the index
    if progress_cb:
        progress_cb("validating", f"Validating {len(candidates)} questions against index")

    validated = []
    for i, question in enumerate(candidates):
        if progress_cb:
            progress_cb("validating", f"Validating question {i + 1}/{len(candidates)}")
        if await _validate_question(question, kb_dir):
            validated.append(question)

    logger.info(
        f"suggestions: {len(validated)}/{len(candidates)} questions passed validation"
    )

    if not validated:
        logger.warning("suggestions: no questions passed validation, returning candidates as fallback")
        return candidates[:15]

    return validated[:15]


async def generate_and_save_suggestions(kb_dir: Path, progress_cb=None) -> None:
    """Generate suggestions, validate them, and save to suggestions.json."""
    suggestions = await generate_suggestions(kb_dir, progress_cb=progress_cb)
    if suggestions:
        out_path = kb_dir / "suggestions.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"suggestions": suggestions}, f, indent=2)
        logger.info(f"suggestions: saved {len(suggestions)} validated suggestions to {out_path}")
    if progress_cb:
        progress_cb("complete", f"Saved {len(suggestions)} suggested questions")


def load_saved_suggestions(kb_dir: Path) -> list[str] | None:
    """Load previously generated suggestions from file, or None if not available."""
    path = kb_dir / "suggestions.json"
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.loads(f.read())
            return data.get("suggestions", [])
    except Exception:
        return None
