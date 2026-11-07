"""Paragraph-aware chunking: ~1200 chars per chunk, ~200 chars overlap.

Chunks never split mid-paragraph if it can be avoided: paragraphs are
accumulated until the target size is reached, then the tail (last ~200
chars, cut at a sentence boundary) is carried into the next chunk so a
fact that straddles a boundary is still retrievable whole.
"""
from __future__ import annotations

import re

TARGET_CHARS = 1200
OVERLAP_CHARS = 200


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def chunk_text(text: str, target: int = TARGET_CHARS,
               overlap: int = OVERLAP_CHARS) -> list[str]:
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paras:
        if len(current) + len(para) + 1 <= target:
            current = f"{current}\n{para}".strip() if current else para
            continue
        if current:
            chunks.append(current)
            # Overlap: carry the tail of the finished chunk forward.
            tail = current[-overlap:]
            cut = max(tail.rfind(". "), tail.rfind("! "), tail.rfind("? "))
            current = tail[cut + 2:] if cut > 20 else tail
            current = current.strip()
        # A single over-long paragraph is split on sentence boundaries.
        while len(para) > target:
            sents = _sentences(para)
            if len(sents) <= 1:
                chunks.append(para[:target])
                para = para[target:]
                break
            acc = ""
            used = 0
            for s in sents:
                if len(acc) + len(s) + 1 > target and acc:
                    break
                acc = f"{acc} {s}".strip()
                used += 1
            chunks.append(acc)
            para = " ".join(sents[used:])
        current = f"{current}\n{para}".strip() if current else para
    if current.strip():
        chunks.append(current.strip())
    return [c for c in chunks if len(c.strip()) > 40]
