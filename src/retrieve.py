"""Hybrid retrieval: semantic (OpenAI embeddings + local/Pinecone store)
fused with keyword BM25 via Reciprocal Rank Fusion, then LLM reranking.

Pipeline per query:
  1. Embed the query and fetch top-8 semantic hits.
  2. Score all chunks with BM25, take its top-8.
  3. Fuse both rankings with RRF (k=60) -> top-8 candidates.
  4. LLM-rerank the 8 candidates with gpt-4o-mini (0-2 relevance
     each) -> top-4. If reranking fails or is unparsable, fall back
     to the RRF order. Reranking can be disabled with rerank=False
     (faster, slightly weaker).
"""
from __future__ import annotations

import json
import re

from .bm25 import BM25
from .openai_client import embed_query, generate

RERANK_PROMPT = """Score how relevant each passage is to the question. Reply with ONLY a JSON list of integers, one per passage, in order. 2 = directly answers the question, 1 = related background, 0 = irrelevant.

Question: {question}

{passages}
"""

RRF_K = 60


def reciprocal_rank_fusion(rankings: list[list[int]], k: int = RRF_K) -> list[int]:
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores, key=lambda i: -scores[i])


def llm_rerank(question: str, chunks: list[dict]) -> list[int] | None:
    """Return chunk positions (into `chunks`) sorted by relevance, or None."""
    passages = "\n\n".join(
        f"[{i}] {c['text'][:600]}" for i, c in enumerate(chunks))
    try:
        raw = generate(RERANK_PROMPT.format(question=question, passages=passages))
    except Exception:
        return None
    m = re.search(r"\[[\d,\s]+\]", raw)
    if not m:
        return None
    try:
        scores = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if len(scores) != len(chunks) or not all(isinstance(s, int) for s in scores):
        return None
    order = sorted(range(len(chunks)), key=lambda i: (-scores[i], i))
    return order


class Retriever:
    def __init__(self, store, chunks: list[dict]):
        self.store = store
        self.chunks = chunks
        self.bm25 = BM25([c["text"] for c in chunks])

    def retrieve(self, question: str, top_k: int = 4, candidate_k: int = 8,
                 rerank: bool = True) -> list[dict]:
        qvec = embed_query(question)
        sem = [i for i, _ in self.store.search(qvec, top_k=candidate_k)]
        bm25_scores = self.bm25.scores(question)
        kw = sorted(range(len(self.chunks)),
                    key=lambda i: -bm25_scores[i])[:candidate_k]
        fused = reciprocal_rank_fusion([sem, kw])[:candidate_k]
        candidates = [self.chunks[i] for i in fused]
        if rerank and len(candidates) > 1:
            order = llm_rerank(question, candidates)
            if order is not None:
                candidates = [candidates[i] for i in order]
        # Diversity cap: at most 2 chunks from any one document in the
        # final top-k. Without it, a long page that matches well (e.g.
        # leave-types) can crowd out the second page a multi-document
        # question needs (e.g. time-off-types for sick leave).
        out = []
        per_doc: dict[str, int] = {}
        for c in candidates:
            if len(out) >= top_k:
                break
            if per_doc.get(c["doc_slug"], 0) >= 2:
                continue
            per_doc[c["doc_slug"]] = per_doc.get(c["doc_slug"], 0) + 1
            out.append({**c, "retrieved_rank": len(out) + 1})
        return out
