# -*- coding: utf-8 -*-
"""Generate suggested questions from indexed chunks using a larger LLM."""
import json
import logging
from pathlib import Path

from backend.config import get_settings
from backend.chat.ollama_client import generate

logger = logging.getLogger(__name__)

_SUGGESTION_PROMPT = """\
You are analyzing resume and portfolio content that has been chunked and indexed.
Below are representative text chunks from this person's documents.

Your task: generate exactly 15 high-quality suggested questions that a recruiter
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

Return ONLY a JSON array of 15 question strings, no other text. Example format:
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


async def generate_suggestions(kb_dir: Path) -> list[str]:
    """Use a larger LLM to generate contextually accurate suggested questions."""
    settings = get_settings()
    chunks_file = kb_dir / "detail" / "chunks.jsonl"

    if not chunks_file.exists():
        return []

    chunk_text = _sample_chunks(chunks_file)
    if not chunk_text:
        return []

    prompt = _SUGGESTION_PROMPT.format(chunks=chunk_text)

    try:
        response = await generate(
            prompt=prompt,
            system="You are a helpful assistant that generates interview questions. Return only valid JSON.",
            model=settings.SUGGESTION_MODEL,
            temperature=0.7,
            max_tokens=2048,
        )

        # Parse JSON array from response
        response = response.strip()
        # Handle models that wrap in markdown code blocks
        if response.startswith("```"):
            response = response.split("\n", 1)[1] if "\n" in response else response
            response = response.rsplit("```", 1)[0].strip()

        suggestions = json.loads(response)
        if isinstance(suggestions, list) and all(isinstance(q, str) for q in suggestions):
            return suggestions[:15]
    except json.JSONDecodeError:
        logger.warning("suggestions: failed to parse LLM response as JSON")
    except Exception as e:
        logger.warning(f"suggestions: LLM generation failed: {e}")

    return []


async def generate_and_save_suggestions(kb_dir: Path) -> None:
    """Generate suggestions and save to suggestions.json in the KB directory."""
    suggestions = await generate_suggestions(kb_dir)
    if suggestions:
        out_path = kb_dir / "suggestions.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"suggestions": suggestions}, f, indent=2)
        logger.info(f"suggestions: saved {len(suggestions)} suggestions to {out_path}")


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
