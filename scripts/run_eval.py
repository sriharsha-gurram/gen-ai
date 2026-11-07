"""Run the 15-question eval end to end and write results.

For each question: retrieve (hybrid + rerank) -> generate cited answer
-> LLM-judge groundedness and fact correctness against the expected fact
and the retrieved passages. Writes data/eval_results.json and
EVAL_REPORT.md. Latency is measured per question (retrieval + generation).

Usage: python -m scripts.run_eval [--no-rerank] [--resume]
Results are saved after every question, so a 429 crash loses nothing;
rerun with --resume to finish the remaining questions.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.eval_questions import QUESTIONS  # noqa: E402
from src.openai_client import generate, usage_summary  # noqa: E402
from src.qa import build_answer  # noqa: E402
from src.retrieve import Retriever  # noqa: E402
from src.vector_store import get_store  # noqa: E402

JUDGE_PROMPT = """You judge a RAG answer. Reply with ONLY one JSON object, no other text:
{{"groundedness": "grounded|partial|ungrounded", "fact": "correct|partial|wrong", "note": "<one sentence>"}}
- groundedness: are ALL factual claims in the answer supported by the retrieved passages? grounded = yes, partial = some claims unsupported, ungrounded = most claims unsupported or invented.
- fact: does the answer contain the expected fact? correct / partial / wrong.
- If the question is unanswerable, "correct" means the answer abstained instead of inventing the fact.

Question: {question}
Expected fact: {expected}
Retrieved passages:
{passages}
Answer:
{answer}
"""


def judge(q: dict, answer: str, retrieved: list[dict]) -> dict:
    passages = "\n\n".join(
        f"[{i + 1}] {c['text'][:800]}" for i, c in enumerate(retrieved))
    raw = generate(JUDGE_PROMPT.format(
        question=q["question"], expected=q["expected_fact"],
        passages=passages, answer=answer))
    try:
        start, end = raw.index("{"), raw.rindex("}") + 1
        return json.loads(raw[start:end])
    except Exception:
        return {"groundedness": "unknown", "fact": "unknown",
                "note": f"unparsable judge output: {raw[:120]}"}


def write_report(results: list[dict], path: Path) -> None:
    """Build EVAL_REPORT.md from the eval results JSON: summary, tables,
    per-question detail, and a failure analysis. Honest numbers only —
    this file is generated from a real run, never hand-written."""
    from datetime import date

    answerable = [r for r in results if r["expected_docs"]]
    unanswerable = [r for r in results if not r["expected_docs"]]
    hits = [r for r in answerable if r["retrieval_hit"]]
    grounded = [r for r in results if r["groundedness"] == "grounded"]
    fact_ok = [r for r in results if r["fact"] == "correct"]
    abstain_ok = [r for r in unanswerable if r["abstained"]]
    lat = sorted(r["latency_s"] for r in results)
    p95 = lat[int(0.95 * len(lat)) - 1] if lat else 0
    n_chunks = len(json.loads(
        (ROOT / "data" / "index" / "chunks.json").read_text())) \
        if (ROOT / "data" / "index" / "chunks.json").exists() else 0
    lines = [
        "# Evaluation Report — Enterprise Policy Q&A Bot",
        "",
        f"Run date: {date.today()}. Corpus: 29 GitLab Handbook People pages, "
        f"{n_chunks} chunks (1200 chars, 200 overlap). Embeddings: "
        "OpenAI text-embedding-3-small (1536-dim). Generation/rerank/judge: "
        "OpenAI gpt-4o-mini. Retrieval: hybrid BM25 + semantic, RRF fusion, "
        "LLM rerank.",
        "",
        "Provider note: the first index was built with Gemini "
        "gemini-embedding-2 and Q01 of this run was originally answered by "
        "Gemini gemini-3-flash-preview (45.9s, grounded, correct). The "
        "Gemini free tier then exhausted (429s), so the index was "
        "re-embedded with OpenAI and Q02-Q15 were run on OpenAI; the "
        "Gemini index is kept in data/index/gemini-archive/.",
        "",
        "## Summary",
        "",
        f"- Questions: {len(results)} "
        f"({len(answerable)} answerable, {len(unanswerable)} unanswerable)",
        f"- Retrieval hit rate (answerable, expected doc in top-4): "
        f"{len(hits)}/{len(answerable)} = "
        f"{100 * len(hits) / max(len(answerable), 1):.0f}%",
        f"- Correct abstention (unanswerable): {len(abstain_ok)}/{len(unanswerable)}",
        f"- Grounded answers (LLM judge): {len(grounded)}/{len(results)}",
        f"- Fact correct (LLM judge): {len(fact_ok)}/{len(results)}",
        f"- Latency: mean {sum(lat) / max(len(lat), 1):.1f}s, "
        f"p95 {p95:.1f}s, max {max(lat) if lat else 0:.1f}s",
        "",
        "## Per-question results",
        "",
        "| ID | Category | Retrieval hit | Fact | Groundedness | Abstained | "
        "Citations valid | Latency |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in results:
        hit = ("yes" if r["retrieval_hit"] else
               "no" if r["retrieval_hit"] is False else "n/a")
        lines.append(
            f"| {r['id']} | {r['category']} | {hit} | {r['fact']} | "
            f"{r['groundedness']} | {r['abstained']} | "
            f"{r.get('citations_valid')} | {r['latency_s']}s |")
    lines += ["", "## Per-question detail", ""]
    for r in results:
        lines += [
            f"### {r['id']} ({r['category']})",
            "",
            f"**Q:** {r['question']}",
            "",
            f"**Expected:** {r['expected_fact']}",
            "",
            f"**Answer:** {r['answer']}",
            "",
            f"**Retrieved docs:** {', '.join(r['retrieved_docs'])} | "
            f"**Judge:** {r['judge_note']}",
            "",
        ]
    failures = [r for r in results
                if r["fact"] != "correct" or r["groundedness"] != "grounded"
                or (r["retrieval_hit"] is False)
                or (not r["expected_docs"] and not r["abstained"])]
    lines += ["## Failure analysis", ""]
    if not failures:
        lines.append("No failures: every question retrieved the expected "
                     "source, stated the expected fact, and was judged "
                     "grounded (with correct abstention on unanswerable "
                     "questions).")
    else:
        for r in failures:
            cause = []
            if r["retrieval_hit"] is False:
                cause.append("retrieval missed the expected doc")
            if r["fact"] != "correct":
                cause.append(f"fact judged {r['fact']}")
            if r["groundedness"] != "grounded":
                cause.append(f"groundedness judged {r['groundedness']}")
            if not r["expected_docs"] and not r["abstained"]:
                cause.append("failed to abstain on an unanswerable question")
            lines.append(f"- **{r['id']}** ({r['category']}): "
                         f"{'; '.join(cause)}. Judge note: {r['judge_note']}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _save(results: list[dict]) -> None:
    (ROOT / "data" / "eval_results.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-rerank", action="store_true")
    parser.add_argument("--resume", action="store_true",
                        help="skip questions already in data/eval_results.json")
    args = parser.parse_args()

    store, backend = get_store(ROOT / "data" / "index")
    if backend == "local-numpy" and not store.load():
        print("No local index found. Run: python -m src.ingest", file=sys.stderr)
        raise SystemExit(1)
    if backend == "pinecone":
        store.chunks = json.loads(
            (ROOT / "data" / "index" / "chunks.json").read_text())
    retriever = Retriever(store, store.chunks)
    results: list[dict] = []
    done_ids: set[str] = set()
    if args.resume:
        prev = ROOT / "data" / "eval_results.json"
        if prev.exists():
            results = json.loads(prev.read_text())
            # Only genuinely completed questions are skipped; error
            # records (e.g. from a 429 crash) are re-run.
            done_ids = {r["id"] for r in results if r.get("fact") != "error"}
            results = [r for r in results if r["id"] in done_ids]
            print(f"Resuming: {len(results)} questions already done.")
    for q in QUESTIONS:
        if q["id"] in done_ids:
            continue
        t0 = time.time()
        try:
            retrieved = retriever.retrieve(q["question"], top_k=4,
                                           rerank=not args.no_rerank)
            result = build_answer(q["question"], retrieved)
            latency = time.time() - t0
            got_docs = [s["doc_slug"] for s in result["sources"]]
            if q["expected_docs"]:
                hit = any(d in got_docs for d in q["expected_docs"])
            else:
                hit = None  # unanswerable: no doc expected
            j = judge(q, result["answer"], retrieved)
            rec = {"id": q["id"], "category": q["category"],
                   "question": q["question"],
                   "expected_fact": q["expected_fact"],
                   "expected_docs": q["expected_docs"],
                   "retrieved_docs": got_docs, "retrieval_hit": hit,
                   "latency_s": round(latency, 1),
                   "abstained": result["abstained"],
                   "citations": result["citations"],
                   "citations_valid": result["citations_valid"],
                   "answer": result["answer"],
                   "groundedness": j.get("groundedness"),
                   "fact": j.get("fact"), "judge_note": j.get("note")}
        except Exception as exc:  # noqa: BLE001 - record and continue
            rec = {"id": q["id"], "category": q["category"],
                   "question": q["question"],
                   "expected_fact": q["expected_fact"],
                   "expected_docs": q["expected_docs"],
                   "retrieved_docs": [], "retrieval_hit": None,
                   "latency_s": round(time.time() - t0, 1),
                   "abstained": False, "citations": [],
                   "citations_valid": False, "answer": "",
                   "groundedness": "error", "fact": "error",
                   "judge_note": f"run failed: {exc}"}
        results.append(rec)
        _save(results)  # incremental: a later 429 loses nothing
        print(f"{q['id']} [{q['category']}] hit={rec['retrieval_hit']} "
              f"fact={rec['fact']} grounded={rec['groundedness']} "
              f"abstained={rec['abstained']} {rec['latency_s']:.0f}s",
              flush=True)
        time.sleep(5)  # gentle on the free tier

    results.sort(key=lambda r: r["id"])
    _save(results)
    write_report(results, ROOT / "EVAL_REPORT.md")
    print(f"\nWrote data/eval_results.json and EVAL_REPORT.md "
          f"({len(results)} questions)")
    print(usage_summary())
    return results


if __name__ == "__main__":
    main()
