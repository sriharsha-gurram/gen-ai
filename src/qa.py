"""Answer generation: cited answers from retrieved chunks only.

Rules enforced by the prompt and checked after generation:
  - Every factual claim must cite a retrieved passage as [1], [2], ...
    where the number is the passage number shown to the model.
  - If the passages do not contain the answer, say so plainly:
    "Not in the knowledge base" — never invent policy numbers, dates,
    or limits. A partial answer states exactly what is covered and
    what is missing.
  - Ambiguous questions get a short clarification of which policy
    reading applies, then the answer for the most likely reading.
"""
from __future__ import annotations

import re

from .openai_client import generate  # OpenAI gpt-4o-mini (Nov 7, 2026 switch; see openai_client.py)

ANSWER_PROMPT = """You answer questions about GitLab company policies using ONLY the passages below. Do not use any other knowledge. Do not invent numbers, dates, limits, or procedures.

Rules:
- Every factual claim must end with a citation like [1] or [2], referring to the passage numbers below.
- If the passages do not contain the answer at all, start your reply exactly with: "Not in the knowledge base: the GitLab Handbook pages in this system do not cover this." and then say what the closest passages do cover, without guessing the missing fact. Use that sentence ONLY when you cannot answer the question at all.
- If the passages cover the question only partially, answer what is covered, cite it, and end with a line starting "Partially covered:" naming what is missing. Do NOT use the "Not in the knowledge base" sentence for a partial answer.
- If the question is ambiguous between policies (for example time off could mean PTO, sick time, or parental leave), briefly name the readings, then answer the most likely one and note the others.
- Keep the answer short: 2-5 sentences plus a one-line note if something is missing.

Question: {question}

Passages:
{passages}
"""

CITATION_RE = re.compile(r"\[(\d+)\]")


def build_answer(question: str, retrieved: list[dict]) -> dict:
    passages = "\n\n".join(
        f"[{i + 1}] (Source: {c['doc_title']} — {c['source_url']})\n{c['text']}"
        for i, c in enumerate(retrieved))
    text = generate(ANSWER_PROMPT.format(question=question, passages=passages))
    # Abstention = the "Not in the knowledge base" sentence opens the
    # answer (within the first 300 chars). A bare contains-check
    # over-fires: the model also uses the phrase as a trailing hedge on
    # partial answers ("Partially covered..."), which is not an
    # abstention. A cited answer also needs at least one citation that
    # actually points at a retrieved passage.
    head = text.strip().lower()[:300]
    abstained = "not in the knowledge base" in head
    cited = sorted({int(n) for n in CITATION_RE.findall(text)})
    valid_citations = [n for n in cited if 1 <= n <= len(retrieved)]
    citations_valid = bool(valid_citations)
    return {
        "answer": text.strip(),
        "abstained": abstained,
        "citations": valid_citations,
        "citations_valid": citations_valid,
        "sources": [
            {"n": i + 1, "doc_slug": c["doc_slug"], "doc_title": c["doc_title"],
             "source_url": c["source_url"], "chunk_id": c["chunk_id"]}
            for i, c in enumerate(retrieved)],
    }
