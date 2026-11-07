"""CLI: ask one question, print the cited answer + sources.

Usage:
  python -m scripts.ask "How many sick days do I get?"
  python -m scripts.ask --no-rerank "How many sick days do I get?"
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.qa import build_answer  # noqa: E402
from src.retrieve import Retriever  # noqa: E402
from src.vector_store import get_store  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("question")
    parser.add_argument("--no-rerank", action="store_true")
    parser.add_argument("--top-k", type=int, default=4)
    args = parser.parse_args()

    store, backend = get_store(ROOT / "data" / "index")
    if backend == "local-numpy" and not store.load():
        print("No local index found. Run: python -m src.ingest", file=sys.stderr)
        raise SystemExit(1)
    if backend == "pinecone":
        store.chunks = json.loads(
            (ROOT / "data" / "index" / "chunks.json").read_text())
    retriever = Retriever(store, store.chunks)
    t0 = time.time()
    retrieved = retriever.retrieve(args.question, top_k=args.top_k,
                                   rerank=not args.no_rerank)
    result = build_answer(args.question, retrieved)
    elapsed = time.time() - t0
    print(f"\n[{backend}] {elapsed:.1f}s\n")
    print(result["answer"])
    print("\nSources:")
    for s in result["sources"]:
        print(f"  [{s['n']}] {s['doc_title']} — {s['source_url']}")
    print(f"\nAbstained: {result['abstained']} | Citations: {result['citations']}")


if __name__ == "__main__":
    main()
