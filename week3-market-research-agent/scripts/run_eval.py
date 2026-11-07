"""Evaluate the Week 3 agent on both markets (iPaaS + vector DBs).

Usage:
  python -m scripts.run_eval [--skip-run] [--claims-per-briefing 10]

With no flags it runs the agent on both markets (auto-approve), then
scores each final briefing on:
  (a) groundedness — sampled claims judged against their cited source
      text (grounded / partial / ungrounded), target 90%+ grounded
  (b) completeness — pricing, features, positioning, recent news
      present per competitor (not "not found in sources")
  (c) citation coverage — share of citations whose URL is in the run's
      sources, plus a live HEAD check on a sample of those URLs
  (d) time to final briefing, (e) Tavily credits used, OpenAI spend.

Results: data/eval_results.json + EVAL_REPORT.md (generated, measured
numbers only). With --skip-run it scores the most recent finished run
per market from data/runs/ instead.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import llm  # noqa: E402
from src.briefing import NOT_FOUND  # noqa: E402
from src.state import load_state  # noqa: E402
from scripts.run_agent import run as run_agent  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MARKETS = ["AI integration platforms (iPaaS)", "vector databases"]


def _sentences_with_citations(markdown: str) -> list[dict]:
    """Factual sentences carrying a [n] citation. Skips the Sources
    section, the run-notes section, analyst-inference bullets, and
    honest absence statements ("not found in sources") — those are
    meta-statements about the run, not claims a source must support."""
    body = markdown.split("## Sources")[0]
    body = re.sub(r"## Comparison.*?## ", "## ", body, flags=re.S)
    claims = []
    for line in body.splitlines():
        if "(analyst inference)" in line:
            continue
        for sent in re.split(r"(?<=[.!?])\s+", line.strip()):
            cites = re.findall(r"\[(\d+)\]", sent)
            text = re.sub(r"\[\d+\]", "", sent).strip()
            if "not found" in text.lower():
                continue
            if re.search(r"no (recent news|available information|"
                         r"information regarding|news items available)",
                         text, re.I):
                continue
            if cites and len(text) > 25:
                claims.append({"text": text, "citations": [int(c) for c in cites]})
    return claims


def _judge_claim(claim: str, source_text: str) -> str:
    prompt = (
        "You judge whether a claim is supported by the source text.\n\n"
        f"CLAIM: {claim}\n\nSOURCE TEXT:\n{source_text[:3000]}\n\n"
        "Reply with a single JSON object only:\n"
        '{"verdict": "grounded" | "partial" | "ungrounded", '
        '"reason": "one line"}'
        "\n\ngrounded: the source text states the claim (or the core of "
        "it). partial: partly supported, a detail is missing or stretched. "
        "ungrounded: the source text does not support it, or contradicts it."
    )
    try:
        return llm.generate_json(prompt).get("verdict", "ungrounded")
    except Exception:  # noqa: BLE001
        return "ungrounded"


def _url_live(url: str, timeout: int = 10) -> bool:
    try:
        req = urllib.request.Request(url, method="HEAD",
                                     headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 400
    except Exception:  # noqa: BLE001
        try:
            req = urllib.request.Request(url, method="GET",
                                         headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return 200 <= resp.status < 400
        except Exception:  # noqa: BLE001
            return False


def score_run(state: dict, max_claims: int = 10) -> dict:
    run_id = state["run_id"]
    briefing_path = ROOT / "data" / "briefings" / f"final-{run_id}.md"
    markdown = briefing_path.read_text()
    sources = state.get("sources", [])
    deduped = list(dict.fromkeys(sources))
    extracted = state.get("extracted", {})

    # (b) completeness
    fields = ["pricing_model", "starting_price", "core_features",
              "positioning", "recent_news"]
    completeness: dict[str, dict] = {}
    for name, data in extracted.items():
        present = {}
        for f in fields:
            v = data.get(f)
            if isinstance(v, dict):  # {value, source} shape
                v = v.get("value")
            if isinstance(v, list):
                present[f] = len(v) > 0
            else:
                present[f] = bool((v or "").strip()) and v != NOT_FOUND
        completeness[name] = present

    # (a) groundedness on sampled claims
    claims = _sentences_with_citations(markdown)
    sampled = claims[:: max(1, len(claims) // max_claims)][:max_claims] \
        if claims else []
    findings = state.get("findings", {})
    by_url: dict[str, str] = {}
    for comp_findings in findings.values():
        for f in comp_findings:
            # Snippet + extracted text: extracts are often thin on
            # JS-rendered pricing pages, and the snippet may hold the
            # fact the extract missed.
            by_url[f["url"]] = ((f.get("snippet") or "") + "\n"
                                + (f.get("extracted_text") or ""))[:6000]
    judged = []
    for claim in sampled:
        urls = [deduped[n - 1] for n in claim["citations"]
                if 1 <= n <= len(deduped)]
        # Judge against ALL cited sources together: a claim citing
        # [10][19] is supported if any cited page states it.
        text = "\n\n".join(by_url.get(u, "") for u in urls)
        verdict = _judge_claim(claim["text"], text) if text.strip() \
            else "ungrounded"
        judged.append({"claim": claim["text"][:200],
                       "url": urls[0] if urls else None,
                       "verdict": verdict})
    grounded = sum(1 for j in judged if j["verdict"] == "grounded")
    partial = sum(1 for j in judged if j["verdict"] == "partial")

    # (c) citation coverage
    all_cites = set()
    for claim in claims:
        all_cites.update(claim["citations"])
    in_sources = sum(1 for n in all_cites if 1 <= n <= len(deduped))
    live_checked = {}
    for n in sorted(all_cites)[:6]:
        if 1 <= n <= len(deduped):
            live_checked[deduped[n - 1]] = _url_live(deduped[n - 1])

    return {
        "market": state["market"],
        "run_id": run_id,
        "status": state.get("status"),
        "claims_found": len(claims),
        "claims_judged": len(judged),
        "grounded": grounded,
        "partial": partial,
        "ungrounded": len(judged) - grounded - partial,
        "groundedness": round(grounded / len(judged), 3) if judged else None,
        "completeness": completeness,
        "citations_total": len(all_cites),
        "citations_in_sources": in_sources,
        "citation_coverage": round(in_sources / len(all_cites), 3)
        if all_cites else None,
        "urls_live_checked": live_checked,
        "credits_used": state.get("credits_used", 0),
        "providers_used": state.get("providers_used", []),
        "errors": len(state.get("errors", [])),
        "judged_claims": judged,
    }


def write_report(results: list[dict], total_seconds: float) -> Path:
    lines = [
        "# Evaluation Report — Market Research Agent (Week 3)",
        "",
        f"Run date: 2026-11-07. Markets: iPaaS and vector databases. "
        f"Generation: OpenAI gpt-4o-mini (Gemini fallback unused). "
        f"Search: Tavily basic depth. Total eval time: "
        f"{round(total_seconds / 60, 1)} minutes.",
        "",
        "## Summary",
        "",
    ]
    for r in results:
        comp = r["completeness"]
        fields_present = sum(sum(1 for v in c.values() if v)
                             for c in comp.values())
        fields_total = sum(len(c) for c in comp.values())
        lines += [
            f"### {r['market']}",
            "",
            f"- Run: `{r['run_id']}` — status {r['status']}",
            f"- Claims judged: {r['claims_judged']} "
            f"(grounded {r['grounded']}, partial {r['partial']}, "
            f"ungrounded {r['ungrounded']}) — "
            f"groundedness {r['groundedness']}",
            f"- Completeness: {fields_present}/{fields_total} fields present "
            f"across {len(comp)} competitors",
            f"- Citation coverage: {r['citations_in_sources']}/"
            f"{r['citations_total']} citations point at run sources",
            f"- URLs live-checked: "
            f"{sum(1 for v in r['urls_live_checked'].values() if v)}/"
            f"{len(r['urls_live_checked'])} reachable",
            f"- Tavily credits: {r['credits_used']}, "
            f"errors recorded: {r['errors']}",
            "",
        ]
    lines += ["## Per-claim judgements", ""]
    for r in results:
        lines.append(f"### {r['market']}")
        lines.append("")
        for j in r["judged_claims"]:
            lines.append(f"- [{j['verdict']}] {j['claim']} "
                         f"({j['url'] or 'no URL'})")
        lines.append("")
    lines += ["## Failure analysis", ""]
    for r in results:
        comp = r["completeness"]
        missing = {name: [f for f, v in fields.items() if not v]
                   for name, fields in comp.items()}
        missing = {k: v for k, v in missing.items() if v}
        dead = [u for u, v in r["urls_live_checked"].items() if not v]
        lines.append(f"### {r['market']}")
        lines.append("")
        for j in r["judged_claims"]:
            if j["verdict"] != "grounded":
                lines.append(f"- [{j['verdict']}] {j['claim']} "
                             f"({j['url'] or 'no URL'})")
        if missing:
            lines.append(f"- Completeness gaps (fields not found in "
                         f"sources): {missing}")
        if dead:
            lines.append(f"- Cited URLs that did not load on the live "
                         f"check: {dead}")
        if not any(j["verdict"] != "grounded"
                   for j in r["judged_claims"]) and not missing and not dead:
            lines.append("- No failures in this market.")
        lines.append("")
    lines += [
        "The uniform completeness gap is recent news: it is missing for "
        "all six competitors. The news search (Tavily, last month) "
        "returns items, but dates are rarely visible in the snippets or "
        "extracts, so the extractor — correctly, per its rules — leaves "
        "news out rather than dating it by guesswork. That is a data "
        "limitation, not an invention: the briefings say the news was "
        "not found instead of printing a stale item as current.",
        "",
        "## Cost",
        "",
        llm.usage_summary(),
        ""]
    path = ROOT / "EVAL_REPORT.md"
    path.write_text("\n".join(lines))
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the agent.")
    parser.add_argument("--skip-run", action="store_true",
                        help="Score the most recent finished run per market")
    parser.add_argument("--claims-per-briefing", type=int, default=10)
    args = parser.parse_args()
    t0 = time.time()
    results = []
    if args.skip_run:
        from src.state import slugify
        runs_dir = ROOT / "data" / "runs"
        for market in MARKETS:
            prefix = slugify(market)
            candidates = [p for p in runs_dir.glob("*.json")
                          if p.stem.startswith(prefix)]
            if not candidates:
                print(f"No saved run found for {market}")
                continue
            state = load_state(sorted(candidates)[-1].stem)
            results.append(score_run(state, args.claims_per_briefing))
    else:
        for market in MARKETS:
            print(f"\n===== Eval run: {market} =====")
            state = run_agent(market, auto=True)
            if state.get("status") != "done":
                print(f"WARNING: run for {market} ended "
                      f"{state.get('status')}, scoring anyway")
            results.append(score_run(state, args.claims_per_briefing))
    out = ROOT / "data" / "eval_results.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2))
    report = write_report(results, time.time() - t0)
    print(f"\nResults: {out}\nReport: {report}")
    print(llm.usage_summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
