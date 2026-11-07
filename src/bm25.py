"""Small pure-Python BM25 (k1=1.5, b=0.75) over chunk text.

No extra dependency. Used as the keyword leg of hybrid retrieval so
queries with exact policy terms ("sick days", "parental leave",
"onboarding buddy") also match on words, not only on embedding geometry.
"""
from __future__ import annotations

import math
import re
from collections import Counter

TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = [tokenize(d) for d in docs]
        self.doc_len = [len(d) for d in self.docs]
        self.avg_len = sum(self.doc_len) / max(len(self.doc_len), 1)
        self.df = Counter()
        for d in self.docs:
            for term in set(d):
                self.df[term] += 1
        self.n = len(self.docs)
        self.tf = [Counter(d) for d in self.docs]

    def _idf(self, term: str) -> float:
        df = self.df.get(term, 0)
        return math.log(1 + (self.n - df + 0.5) / (df + 0.5))

    def scores(self, query: str) -> list[float]:
        qterms = tokenize(query)
        out = []
        for i in range(self.n):
            score = 0.0
            dl = self.doc_len[i]
            for term in qterms:
                tf = self.tf[i].get(term, 0)
                if not tf:
                    continue
                denom = tf + self.k1 * (1 - self.b + self.b * dl / self.avg_len)
                score += self._idf(term) * tf * (self.k1 + 1) / denom
            out.append(score)
        return out
