"""Vector stores.

Default: LocalNumpyStore — vectors + chunk metadata persisted locally
(data/index/vectors.npz + data/index/chunks.json), cosine similarity in
numpy. No extra service, no extra key, works offline once indexed.

Optional: PineconeStore — same interface, backed by Pinecone. Requires
PINECONE_API_KEY (and PINECONE_INDEX, default "gitlab-policy-qa").
No key is bundled or stored in this repo; see .env.example. The app
falls back to the local store when no key is set.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np


class LocalNumpyStore:
    def __init__(self, index_dir: str | Path):
        self.dir = Path(index_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.vectors: np.ndarray | None = None
        self.chunks: list[dict] = []

    def build(self, chunks: list[dict], vectors: list[list[float]]) -> None:
        arr = np.array(vectors, dtype=np.float32)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        self.vectors = arr / np.maximum(norms, 1e-9)
        self.chunks = chunks
        np.savez_compressed(self.dir / "vectors.npz", vectors=self.vectors)
        (self.dir / "chunks.json").write_text(json.dumps(chunks), encoding="utf-8")

    def load(self) -> bool:
        vpath = self.dir / "vectors.npz"
        cpath = self.dir / "chunks.json"
        if not vpath.exists() or not cpath.exists():
            return False
        self.vectors = np.load(vpath)["vectors"]
        self.chunks = json.loads(cpath.read_text(encoding="utf-8"))
        return True

    def search(self, query_vector: list[float], top_k: int = 8) -> list[tuple[int, float]]:
        if self.vectors is None:
            raise RuntimeError("Index not loaded. Run ingest first.")
        q = np.array(query_vector, dtype=np.float32)
        q = q / max(np.linalg.norm(q), 1e-9)
        sims = self.vectors @ q
        idx = np.argsort(-sims)[:top_k]
        return [(int(i), float(sims[i])) for i in idx]


class PineconeStore:
    """Optional Pinecone backend. Only constructed when a key is present."""

    def __init__(self, index_name: str | None = None):
        import pinecone  # lazy: pinecone-client is an optional dependency

        api_key = os.environ.get("PINECONE_API_KEY")
        if not api_key:
            raise RuntimeError("PINECONE_API_KEY is not set")
        self.pc = pinecone.Pinecone(api_key=api_key)
        self.index_name = index_name or os.environ.get(
            "PINECONE_INDEX", "gitlab-policy-qa")
        existing = [i["name"] for i in self.pc.list_indexes()]
        if self.index_name not in existing:
            self.pc.create_index(
                name=self.index_name, dimension=3072, metric="cosine",
                spec=pinecone.ServerlessSpec(cloud="aws", region="us-east-1"))
        self.index = self.pc.Index(self.index_name)
        self.chunks: list[dict] = []

    def build(self, chunks: list[dict], vectors: list[list[float]]) -> None:
        self.chunks = chunks
        batch = []
        for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
            batch.append({"id": f"chunk-{i}", "values": vec,
                          "metadata": {"doc": chunk["doc_slug"],
                                       "title": chunk["doc_title"]}})
            if len(batch) == 100:
                self.index.upsert(vectors=batch)
                batch = []
        if batch:
            self.index.upsert(vectors=batch)

    def search(self, query_vector: list[float], top_k: int = 8) -> list[tuple[int, float]]:
        res = self.index.query(vector=query_vector, top_k=top_k,
                               include_metadata=False)
        out = []
        for m in res.get("matches", []):
            i = int(m["id"].split("-")[1])
            out.append((i, float(m["score"])))
        return out


def get_store(index_dir: str | Path = "data/index"):
    """Pinecone when PINECONE_API_KEY is set, otherwise the local store."""
    if os.environ.get("PINECONE_API_KEY"):
        try:
            return PineconeStore(), "pinecone"
        except Exception as exc:  # noqa: BLE001 - fall back, never block
            print(f"Pinecone unavailable ({exc}); using local store.")
    return LocalNumpyStore(index_dir), "local-numpy"
