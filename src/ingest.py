"""Ingest: data/raw/*.md -> chunks -> OpenAI embeddings -> local index.

Usage:  python -m src.ingest [--reindex]
Reads the corpus manifest, chunks every raw document (1200 chars,
200 overlap), batch-embeds with text-embedding-3-small (1536-dim),
and writes data/index/chunks.json + data/index/vectors.npz. With
--reindex it rebuilds even if an index already exists.

Provider history (Nov 7, 2026): the first index was built with Gemini
gemini-embedding-2, but the Gemini free tier then exhausted (429s on
both embeddings and generation, stalling the eval at Q01). The user
reloaded $5 of OpenAI API credit, so the index was re-embedded with
OpenAI text-embedding-3-small and generation/rerank/judge moved to
gpt-4o-mini. The Gemini index is kept aside in
data/index/gemini-archive/ (chunks.json, vectors.npz, partials).
Query embeddings must use the same model as the index — never mix.

Resumable: each embedding batch is checkpointed to
data/index/partials/batch_XXX.npy as soon as it succeeds, so an
interrupted run resumes where it stopped instead of starting over.
Rerun the same command to continue. Run ONE ingest at a time.

Partials are tied to a corpus fingerprint (chunk ids + sizes + text
prefixes, stored in partials/_fingerprint.json). If the corpus or the
chunking changes, the fingerprint mismatches and stale partials are
deleted instead of being silently reused.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.chunking import chunk_text  # noqa: E402
from src.openai_client import embed_texts  # noqa: E402
from src.vector_store import LocalNumpyStore  # noqa: E402

BATCH_SIZE = 100  # OpenAI /v1/embeddings accepts a list of inputs


def load_documents(root: Path) -> list[dict]:
    manifest = json.loads((root / "data" / "corpus_manifest.json").read_text())
    docs = []
    for d in manifest["documents"]:
        path = root / d["file"]
        if not path.exists():
            print(f"  missing raw file, skipping: {d['file']}")
            continue
        raw = path.read_text(encoding="utf-8")
        lines = raw.splitlines()
        body = "\n".join(lines[4:]) if len(lines) > 4 else raw
        docs.append({**d, "body": body})
    return docs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reindex", action="store_true")
    args = parser.parse_args()
    index_dir = ROOT / "data" / "index"
    partials_dir = index_dir / "partials"
    partials_dir.mkdir(parents=True, exist_ok=True)
    if (index_dir / "chunks.json").exists() and not args.reindex:
        print("Index already exists. Use --reindex to rebuild.")
        return
    if args.reindex and (index_dir / "chunks.json").exists():
        # Fresh rebuild: drop old checkpoints so stale batches cannot leak in.
        for p in partials_dir.glob("batch_*.npy"):
            p.unlink()
        (index_dir / "chunks.json").unlink(missing_ok=True)
        (index_dir / "vectors.npz").unlink(missing_ok=True)
    docs = load_documents(ROOT)
    chunks: list[dict] = []
    for d in docs:
        for i, text in enumerate(chunk_text(d["body"])):
            chunks.append({
                "chunk_id": f"{d['slug']}#{i}",
                "doc_slug": d["slug"], "doc_title": d["title"],
                "source_url": d["url"], "text": text,
            })
    print(f"{len(docs)} docs -> {len(chunks)} chunks")
    # Corpus fingerprint: partials are only reusable for this exact chunk set.
    fingerprint = hashlib.sha256("\n".join(
        f"{c['chunk_id']}|{len(c['text'])}|{c['text'][:80]}"
        for c in chunks).encode()).hexdigest()[:16]
    fp_path = partials_dir / "_fingerprint.json"
    if fp_path.exists():
        stored = json.loads(fp_path.read_text()).get("fingerprint")
        if stored != fingerprint:
            print("Corpus/chunking changed — discarding stale partials.")
            for p in partials_dir.glob("batch_*.npy"):
                p.unlink()
    fp_path.write_text(json.dumps({"fingerprint": fingerprint,
                                   "n_chunks": len(chunks)}))
    print("Embedding with text-embedding-3-small (100/batch, checkpointed)...")
    n_batches = (len(chunks) + BATCH_SIZE - 1) // BATCH_SIZE
    all_vectors: list[np.ndarray] = []
    for b in range(n_batches):
        part_path = partials_dir / f"batch_{b:03d}.npy"
        if part_path.exists():
            all_vectors.append(np.load(part_path))
            continue
        batch = chunks[b * BATCH_SIZE:(b + 1) * BATCH_SIZE]
        vectors = embed_texts([c["text"] for c in batch])
        arr = np.array(vectors, dtype=np.float32)
        np.save(part_path, arr)
        all_vectors.append(arr)
        print(f"  batch {b + 1}/{n_batches} done ({len(chunks)} chunks total)")
    vectors = np.concatenate(all_vectors, axis=0)
    assert vectors.shape[0] == len(chunks), (
        f"vector/chunk mismatch: {vectors.shape[0]} vs {len(chunks)}")
    store = LocalNumpyStore(index_dir)
    store.build(chunks, vectors.tolist())
    print(f"Index written: {index_dir}/chunks.json + vectors.npz "
          f"({len(chunks)} chunks, 1536-dim)")
    from src.openai_client import usage_summary  # noqa: E402
    print(usage_summary())


if __name__ == "__main__":
    main()
