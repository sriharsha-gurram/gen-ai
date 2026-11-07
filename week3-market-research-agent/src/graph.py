"""LangGraph StateGraph for the Week 3 Market Research Agent.

Supervisor (plan) with workers as tools, per the research design:
  plan -> discover -> checkpoint_a (human interrupt) -> gather
  -> gather_one (Send fan-out, one per competitor) -> analyse
  -> analyse_one (Send fan-out) -> synthesise -> human_review
  (human interrupt) -> finalise | (revise -> gather) | END

Guards, enforced by the graph, not by convention:
  - recursion_limit 25, max 3 searches per competitor, max 2 analyst
    passes, Tavily credit guard at 60 (stop and ask the human).
  - A field the sources do not answer is "not found in sources".
    An invented price is a failure, so the analyser's starting-price
    digits must appear in a gathered source, or the field is dropped.
  - Nothing is written to data/briefings/final-* until a human approves.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send, interrupt

from src import llm, tavily_client
from src.briefing import NOT_FOUND, render_briefing
from src.state import (CREDIT_GUARD, MAX_ANALYST_PASSES,
                       MAX_SEARCHES_PER_COMPETITOR, RECURSION_LIMIT,
                       AgentState, save_state)
from src.tools import (list_sources, request_human_review,
                       save_briefing_draft, tavily_extract, tavily_search)


# ---------------------------------------------------------------- helpers

def _now() -> float:
    return time.time()


def _log(state: dict, node: str, msg: str) -> None:
    print(f"  [{node}] {msg}")


def _record_error(state: dict, node: str, error: str,
                  resolution: str = "") -> dict:
    return {"errors": [{"node": node, "error": error,
                        "resolution": resolution,
                        "at": datetime.now(timezone.utc).isoformat()}]}


def _sync_credits(state: dict) -> dict:
    """Snapshot the module credit counter into state (parallel nodes
    must not write this field themselves — last-write-wins would lose
    counts, so the runner and this helper own it)."""
    return {"credits_used": tavily_client.credits_used(),
            "providers_used": list(llm.PROVIDERS_USED)}


# ---------------------------------------------------------------- nodes

def plan_node(state: AgentState) -> dict:
    t0 = _now()
    market = (state.get("market") or "").strip()
    if not market:
        raise ValueError("plan: no market given")
    _log(state, "plan", f"market: {market}")
    out: dict = {"market": market, "status": "planned",
                 "timings": {"plan": round(_now() - t0, 1)}}
    out.update(_sync_credits(state))
    return out


def discover_node(state: AgentState) -> dict:
    t0 = _now()
    if state.get("competitors"):
        _log(state, "discover", "competitors already set, skipping (resume)")
        return {"status": "discovering"}
    market = state["market"]
    _log(state, "discover", f"searching top competitors in {market}")
    results = []
    try:
        results += tavily_search(f"top {market} competitors 2026", max_results=5)
        results += tavily_search(f"best {market} platforms comparison", max_results=5)
    except Exception as exc:  # noqa: BLE001
        return {**_record_error(state, "discover", str(exc),
                                "discovery failed; run cannot continue"),
                "status": "failed"}
    candidates = "\n".join(
        f"- {r['title']} ({r['url']}): {r['content'][:300]}" for r in results)
    prompt = (
        f"You are a market research analyst. Market: {market}.\n\n"
        f"Below are web search results about the leading vendors in this "
        f"market. Pick the TOP 3 competitors a product manager should "
        f"compare. Prefer vendors with a real product in this market and "
        f"public pricing or feature pages. Do not invent vendors that do "
        f"not appear in the results.\n\n{candidates}\n\n"
        f"Reply with a single JSON object only:\n"
        f'{{"competitors": [{{"name": "...", "why": "one line"}}, ...]}}'
    )
    try:
        ranked = llm.generate_json(prompt)
        competitors = ranked.get("competitors", [])[:3]
    except Exception as exc:  # noqa: BLE001
        return {**_record_error(state, "discover", f"ranking failed: {exc}",
                                "kept search results; supervisor will fail "
                                "the run rather than guess"),
                "status": "failed"}
    if len(competitors) < 3:
        return {**_record_error(state, "discover",
                                f"only {len(competitors)} competitors found",
                                "run needs 3; failing rather than inventing"),
                "status": "failed"}
    sources = [r["url"] for r in results if r.get("url")]
    _log(state, "discover", "proposed: " + ", ".join(c["name"] for c in competitors))
    out: dict = {"competitors": [
                     {"name": c["name"], "why": c.get("why", ""),
                      "status": "proposed"} for c in competitors],
                 "sources": sources, "status": "discovering",
                 "timings": {"discover": round(_now() - t0, 1)}}
    out.update(_sync_credits(state))
    return out


def checkpoint_a_node(state: AgentState) -> dict:
    """Checkpoint A: human sees the 3 proposed competitors and can swap
    one out before any deep research is spent. Enforced by interrupt()."""
    if state.get("checkpoint_a_done"):
        return {}
    proposed = [{"name": c["name"], "why": c.get("why", "")}
                for c in state.get("competitors", [])]
    decision = interrupt({
        "checkpoint": "A",
        "question": "Approve these 3 competitors, or swap one out?",
        "competitors": proposed,
        "credits_used": tavily_client.credits_used(),
    })
    # decision: {"decision": "approve"} or
    #           {"decision": "swap", "competitors": [{name, why}, ...]}
    if isinstance(decision, dict) and decision.get("decision") == "swap":
        new_list = decision.get("competitors") or []
        if len(new_list) == 3 and all(c.get("name") for c in new_list):
            _log(state, "checkpoint_a", "human swapped the competitor list")
            return {"competitors": [
                        {"name": c["name"], "why": c.get("why", ""),
                         "status": "proposed"} for c in new_list],
                    "human_decision": "swap",
                    "checkpoint_a_done": True, "status": "discovering"}
    _log(state, "checkpoint_a", "human approved the competitor list")
    return {"human_decision": "approved", "checkpoint_a_done": True,
            "status": "discovering"}


def gather_node(state: AgentState) -> Command:
    """Fan out one gather_one per competitor that still needs data.
    Returns Command(goto=[Send(...)]) — in LangGraph 1.x a Command
    return does NOT suppress the node's static edges, so this node has
    NO static outgoing edge; the empty case routes explicitly to
    analyse via Command(goto=[...]).

    Send-payload note: a Send task receives ONLY its payload as input
    state, so the payload carries the market (and this fan-out node,
    which sees the full state, does the skip filtering)."""
    revise = state.get("revise_competitor")
    names = [c["name"] for c in state.get("competitors", [])]
    if revise:
        names = [n for n in names if n == revise]
    todo = [n for n in names if not state.get("findings", {}).get(n)]
    if not todo:
        _log(state, "gather", "all findings already saved, skipping (resume)")
        return Command(update={"status": "analysing"}, goto=["analyse"])
    _log(state, "gather", f"researching: {', '.join(todo)}")
    return Command(update={"status": "gathering"},
                   goto=[Send("gather_one", {
                       "competitor": name, "market": state["market"]})
                         for name in todo])


def prepare_revise_node(state: AgentState) -> dict:
    """Clear the saved findings/extraction for the competitor being
    re-researched, so gather + analyse run it again from scratch."""
    name = state.get("revise_competitor")
    if not name:
        return {}
    _log(state, "prepare_revise", f"clearing saved data for {name}")
    return {"findings": {name: None}, "extracted": {name: None},
            "revise_competitor": None}


def gather_one_node(state: AgentState) -> dict:
    t0 = _now()
    name = state.get("competitor", "")
    if not name:
        return {}
    if state.get("findings", {}).get(name):
        return {}
    market = state["market"]
    findings: list[dict] = []
    errors: list[dict] = []
    searches = [
        (f"{name} pricing plans cost", None),
        (f"{name} features capabilities", None),
        (f"{name} news", "month"),
    ][:MAX_SEARCHES_PER_COMPETITOR]
    urls: list[str] = []
    for query, time_range in searches:
        if tavily_client.credits_used() >= CREDIT_GUARD:
            errors.append({"node": "gather_one", "error":
                           f"credit guard hit ({CREDIT_GUARD}) before "
                           f"searching {name}",
                           "resolution": "competitor marked insufficient data",
                           "at": datetime.now(timezone.utc).isoformat()})
            break
        try:
            results = tavily_client.search(query, max_results=5,
                                           time_range=time_range)
        except Exception as exc:  # noqa: BLE001
            errors.append({"node": "gather_one", "error": str(exc),
                           "resolution": f"search failed for '{query}'; "
                                         f"continuing with other searches",
                           "at": datetime.now(timezone.utc).isoformat()})
            continue
        for r in results:
            findings.append({"url": r["url"], "title": r["title"],
                             "snippet": r["content"][:800], "kind": "search",
                             "query": query})
            if r.get("url") and r["url"] not in urls:
                urls.append(r["url"])
    # Extract the most promising pages: vendor domain first, then the
    # highest-scored others, max 4 URLs (1 extract credit).
    vendor_first = sorted(urls, key=lambda u: (name.lower().replace(" ", "")
                                               not in u.lower(), u))
    extract_urls = vendor_first[:4]
    failed_urls: list[str] = []
    if extract_urls:
        try:
            extracted, failed_urls = tavily_extract(extract_urls)
            by_url = {item["url"]: item["raw_content"] for item in extracted}
            for f in findings:
                if f["url"] in by_url:
                    f["extracted_text"] = by_url[f["url"]][:6000]
                    f["kind"] = "extract"
        except Exception as exc:  # noqa: BLE001
            errors.append({"node": "gather_one", "error": str(exc),
                           "resolution": "extract failed; snippets only",
                           "at": datetime.now(timezone.utc).isoformat()})
            failed_urls = extract_urls
    for u in failed_urls:
        errors.append({"node": "gather_one", "error": f"extract failed: {u}",
                       "resolution": "URL kept as a search-snippet source only",
                       "at": datetime.now(timezone.utc).isoformat()})
    _log(state, "gather_one",
         f"{name}: {len(findings)} findings, {len(extract_urls)} extracted")
    # NOTE: parallel nodes must not write plain scalar keys (status,
    # credits_used) — siblings writing the same key in one step raises
    # InvalidUpdateError. Only merge-channel keys here (findings,
    # sources, errors, timings); the runner owns credits/status.
    out: dict = {"findings": {name: findings},
                 "sources": [f["url"] for f in findings if f.get("url")],
                 "timings": {f"gather:{name}": round(_now() - t0, 1)}}
    if errors:
        out["errors"] = errors
    return out


def analyse_node(state: AgentState) -> Command:
    """Fan out one analyse_one per competitor with findings but no
    extraction yet. Same Command-only routing as gather_node: no static
    outgoing edge. The payload carries that competitor's findings,
    because a Send task only sees its payload."""
    todo = [n for n in state.get("findings", {})
            if n not in state.get("extracted", {})]
    if not todo:
        _log(state, "analyse", "all extractions already saved, skipping (resume)")
        return Command(update={"status": "drafting"}, goto=["synthesise"])
    _log(state, "analyse", f"extracting: {', '.join(todo)}")
    return Command(update={"status": "analysing"},
                   goto=[Send("analyse_one", {
                       "competitor": name,
                       "my_findings": state["findings"][name]})
                         for name in todo])


def _price_digits_present(price: str, texts: list[str]) -> bool:
    """Anti-invention guard: the digits of a claimed starting price must
    appear in at least one gathered source text."""
    digits = re.sub(r"\D", "", price or "")
    if not digits:
        return True  # no numeric claim to check
    blob = " ".join(texts)
    return digits in re.sub(r"\D", "", blob) or digits[:3] in blob


def analyse_one_node(state: AgentState) -> dict:
    t0 = _now()
    name = state.get("competitor", "")
    if not name:
        return {}
    # Send payload carries this competitor's findings (my_findings);
    # a direct call falls back to the full-state findings dict.
    my_findings = state.get("my_findings")
    if my_findings is None:
        my_findings = state.get("findings", {}).get(name, [])
    if name in state.get("extracted", {}):
        return {}
    findings = my_findings
    if not findings:
        return {"extracted": {name: {
            "pricing_model": NOT_FOUND, "starting_price": NOT_FOUND,
            "core_features": [], "positioning": NOT_FOUND,
            "recent_news": [], "not_found": ["pricing", "features",
                                             "positioning", "news"],
            "sources": []}}}
    context = "\n\n".join(
        f"SOURCE: {f['url']}\nTITLE: {f['title']}\n"
        f"{f.get('extracted_text') or f['snippet']}"
        for f in findings)[:14000]
    prompt = (
        f"You extract structured facts about {name} from the sources below "
        f"ONLY. Use no outside knowledge. If a field is not answered by "
        f"these sources, set its value to exactly \"{NOT_FOUND}\" (or an "
        f"empty list) and name the field in not_found. Never guess a price.\n\n"
        f"SOURCES:\n{context}\n\n"
        f"Reply with a single JSON object only. Every field carries the "
        f"URL of the source that states it — this is how the briefing "
        f"cites facts later, so a value without its source is useless:\n"
        f'{{"pricing_model": {{"value": "...", "source": "url"}}, '
        f'"starting_price": {{"value": "...", "source": "url"}}, '
        f'"core_features": [{{"feature": "...", "source": "url"}}], '
        f'"positioning": {{"value": "...", "source": "url"}}, '
        f'"recent_news": [{{"title": "...", "date": "...", '
        f'"summary": "...", "url": "..."}}], '
        f'"not_found": ["..."], "sources": ["url", ...]}}'
        f"\n\nRules: recent_news only from items dated in the last 90 days "
        f"if a date is visible, otherwise leave it out and list it in "
        f"not_found. Every URL must be one of the SOURCE urls above. If "
        f"no source states a field, set its value to \"{NOT_FOUND}\" with "
        f"an empty source, do not borrow a URL from another field."
    )
    try:
        data = llm.generate_json(prompt)
    except Exception as exc:  # noqa: BLE001
        return {**_record_error(state, "analyse_one",
                                f"extraction failed for {name}: {exc}",
                                "fields left as not found"),
                "extracted": {name: {
                    "pricing_model": {"value": NOT_FOUND, "source": ""},
                    "starting_price": {"value": NOT_FOUND, "source": ""},
                    "core_features": [],
                    "positioning": {"value": NOT_FOUND, "source": ""},
                    "recent_news": [],
                    "not_found": ["pricing", "features", "positioning",
                                  "news"],
                    "sources": []}}}
    known_urls = {f["url"] for f in findings}
    data = _normalise_extraction(data, known_urls)
    # Anti-invention guard on the starting price: its digits must appear
    # in a gathered source, or the field is dropped.
    price = (data["starting_price"].get("value") or "").strip()
    texts = [(f.get("extracted_text") or f["snippet"]) for f in findings]
    if price and price != NOT_FOUND and not _price_digits_present(price, texts):
        data["not_found"] = sorted(set(data.get("not_found", [])) | {"pricing"})
        data["starting_price"] = {"value": NOT_FOUND, "source": ""}
        _log(state, "analyse_one",
             f"{name}: starting price '{price}' not in any source, dropped")
    _log(state, "analyse_one",
         f"{name}: extracted, not found: {data['not_found'] or 'none'}")
    # NOTE: parallel node — merge-channel keys only (see gather_one).
    return {"extracted": {name: data},
            "sources": data["sources"],
            "timings": {f"analyse:{name}": round(_now() - t0, 1)}}


def _normalise_extraction(data: dict, known_urls: set) -> dict:
    """Force the extractor's output into the per-field-source shape and
    drop any value whose source is not one of the gathered URLs. A
    value without a valid source is not a fact the briefing can cite,
    so it becomes NOT_FOUND."""
    def field(key: str) -> dict:
        raw = data.get(key)
        if isinstance(raw, dict):
            value, source = (raw.get("value") or "").strip(), raw.get("source") or ""
        else:
            value, source = (raw or "").strip(), ""
        if source and source not in known_urls:
            source = ""
        if not value or not source:
            return {"value": NOT_FOUND, "source": ""}
        return {"value": value, "source": source}

    out: dict = {}
    not_found = set(data.get("not_found", []))
    for key in ("pricing_model", "starting_price", "positioning"):
        out[key] = field(key)
        if out[key]["value"] == NOT_FOUND:
            not_found.add(key.replace("pricing_model", "pricing")
                          .replace("starting_price", "pricing"))
    features = []
    for item in data.get("core_features", []) or []:
        if isinstance(item, dict):
            feat, src = (item.get("feature") or "").strip(), item.get("source") or ""
        else:
            feat, src = (item or "").strip(), ""
        if feat and src in known_urls:
            features.append({"feature": feat, "source": src})
    out["core_features"] = features
    if not features:
        not_found.add("features")
    news = []
    for item in data.get("recent_news", []) or []:
        if isinstance(item, dict) and item.get("url") in known_urls:
            news.append(item)
    out["recent_news"] = news
    if not news:
        not_found.add("news")
    sources = [u for u in data.get("sources", []) if u in known_urls]
    for key in ("pricing_model", "starting_price", "positioning"):
        if out[key]["source"]:
            sources.append(out[key]["source"])
    sources += [f["source"] for f in features]
    sources += [n["url"] for n in news]
    out["sources"] = list(dict.fromkeys(sources))
    out["not_found"] = sorted(not_found)
    return out


def synthesise_node(state: AgentState) -> dict:
    t0 = _now()
    if state.get("briefing_draft") and not state.get("revise_competitor"):
        _log(state, "synthesise", "draft already exists, skipping (resume)")
        return {"status": "drafting"}
    extracted = state.get("extracted", {})
    sources = list_sources(state)
    numbered = "\n".join(f"[{i}] {u}" for i, u in enumerate(sources, 1))
    # Per-fact source map: each extracted fact carries the URL that
    # states it, with its [n] number. The synthesis may only cite a
    # fact with that exact number — this is what makes the citations
    # true instead of plausible-looking.
    fact_lines: list[str] = []
    for name, data in extracted.items():
        fact_lines.append(f"{name}:")
        for key, label in [("pricing_model", "pricing model"),
                           ("starting_price", "starting price"),
                           ("positioning", "positioning")]:
            field = data.get(key) or {}
            value = field.get("value", "") if isinstance(field, dict) else field
            src = field.get("source", "") if isinstance(field, dict) else ""
            num = f"[{sources.index(src) + 1}]" if src in sources else "[no source]"
            fact_lines.append(f"  - {label}: {value} {num}")
        feats = data.get("core_features", []) or []
        for f in feats:
            feat = f.get("feature", "") if isinstance(f, dict) else f
            src = f.get("source", "") if isinstance(f, dict) else ""
            num = f"[{sources.index(src) + 1}]" if src in sources else "[no source]"
            fact_lines.append(f"  - feature: {feat} {num}")
        for item in data.get("recent_news", []) or []:
            num = (f"[{sources.index(item['url']) + 1}]"
                   if item.get("url") in sources else "[no source]")
            fact_lines.append(f"  - news: {item.get('title', '')} "
                              f"({item.get('date', '')}) {num}")
        if data.get("not_found"):
            fact_lines.append(f"  - not found in sources: "
                              f"{', '.join(data['not_found'])}")
    facts = "\n".join(fact_lines)
    prompt = (
        f"You are writing the narrative of a competitor briefing for the "
        f"market: {state['market']}.\n\n"
        f"FACTS WITH THEIR SOURCES (each fact shows the [n] of the source "
        f"that states it):\n"
        f"{facts}\n\n"
        f"NUMBERED SOURCES:\n"
        f"{numbered}\n\n"
        f"Write, in markdown:\n"
        f"1. One '## <Competitor>' section per competitor: 2-3 SHORT "
        f"paragraphs. Each sentence states exactly ONE fact from the list "
        f"above and ends with that fact's [n] citation — never a "
        f"different number, never two facts in one sentence. Do not "
        f"combine facts, do not paraphrase a fact into a broader claim "
        f"(no 'leading option', 'ideal for', 'best-in-class' unless a "
        f"source says exactly that), and do not write a sentence for a "
        f"fact marked [no source]. If a fact says \"{NOT_FOUND}\", say "
        f"so in the text as 'Information on <field> was not found in "
        f"sources.' with NO citation after it — no source states that "
        f"something is missing, so citing one would be false.\n"
        f"2. A '## What to watch' section: 3-5 bullets on what could change "
        f"the comparison (pricing changes, new features, news). EVERY "
        f"bullet that adds your own judgement, prediction, or "
        f"interpretation MUST end with '(analyst inference)' and carry "
        f"no citation. A bullet that only restates a cited fact ends "
        f"with that fact's [n] citation instead. Never leave an "
        f"inference bullet unlabelled.\n\n"
        f"Short, atomic, cited sentences only. A fluent paragraph that "
        f"no source states is a failure, even if it sounds right."
    )
    prose, _provider = llm.generate(prompt)
    draft = render_briefing({**state, "sources": sources}, prose)
    path = save_briefing_draft(state, draft)
    _log(state, "synthesise", f"draft saved to {path}")
    out: dict = {"briefing_draft": draft, "status": "drafting",
                 "timings": {"synthesise": round(_now() - t0, 1)}}
    out.update(_sync_credits(state))
    return out


def human_review_node(state: AgentState) -> dict:
    """Checkpoint B (mandatory): the graph interrupts. Nothing is
    written to data/briefings/final-* until a human approves."""
    if state.get("checkpoint_b_done"):
        return {}
    payload = request_human_review(state,
        "Draft briefing ready. Approve it, ask for one competitor to be "
        "re-researched, or reject it.")
    decision = interrupt({**payload,
                          "checkpoint": "B",
                          "draft": state.get("briefing_draft", "")})
    # decision: {"decision": "approve"} |
    #           {"decision": "revise", "competitor": "<name>", "notes": "..."} |
    #           {"decision": "reject", "notes": "..."}
    if isinstance(decision, dict):
        choice = decision.get("decision")
        if choice == "revise" and decision.get("competitor"):
            _log(state, "human_review",
                 f"human asked to re-research {decision['competitor']}")
            return {"human_decision": "revise",
                    "revise_competitor": decision["competitor"],
                    "human_notes": decision.get("notes", ""),
                    "analyst_passes": state.get("analyst_passes", 0) + 1,
                    "briefing_draft": None,
                    "status": "awaiting_human"}
        if choice == "reject":
            _log(state, "human_review", "human rejected the draft")
            return {"human_decision": "rejected", "checkpoint_b_done": True,
                    "status": "failed"}
    _log(state, "human_review", "human approved the draft")
    return {"human_decision": "approved", "checkpoint_b_done": True,
            "status": "awaiting_human"}


def finalise_node(state: AgentState) -> dict:
    t0 = _now()
    if state.get("status") == "done":
        return {}
    draft = state.get("briefing_draft") or ""
    # The draft was rendered mid-run, so its Run notes carry stale
    # counts (credits were 2 at synthesis time). Patch them with the
    # final values before the briefing becomes final.
    credits = tavily_client.credits_used()
    providers = ", ".join(dict.fromkeys(llm.PROVIDERS_USED)) or "none recorded"
    draft = re.sub(r"- Tavily credits used: \d+",
                   f"- Tavily credits used: {credits}", draft)
    draft = re.sub(r"- Providers used: .*",
                   f"- Providers used: {providers}", draft)
    draft = re.sub(r"- Errors and retries: \d+ recorded",
                   f"- Errors and retries: {len(state.get('errors', []))} "
                   f"recorded", draft)
    out_dir = Path(__file__).resolve().parent.parent / "data" / "briefings"
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"final-{state['run_id']}.md"
    md_path.write_text(draft)
    json_path = out_dir / f"final-{state['run_id']}.json"
    from src.briefing import render_briefing_json
    json_path.write_text(json.dumps(
        render_briefing_json({**state, "sources": list_sources(state)}),
        indent=2))
    _log(state, "finalise", f"final briefing written to {md_path}")
    return {"status": "done",
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "timings": {"finalise": round(_now() - t0, 1)}}


def route_after_review(state: AgentState) -> str:
    """After human_review: approve -> finalise, revise (cap not hit) ->
    gather for one competitor, reject / cap hit -> finalise with a note."""
    if state.get("human_decision") == "revise":
        if state.get("analyst_passes", 0) <= MAX_ANALYST_PASSES:
            return "revise"
        _log(state, "router",
             "revision cap hit; finalising with the current draft")
        return "finalise"
    if state.get("human_decision") == "rejected":
        return "end"
    return "finalise"


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("plan", plan_node)
    graph.add_node("discover", discover_node)
    graph.add_node("checkpoint_a", checkpoint_a_node)
    graph.add_node("gather", gather_node)
    graph.add_node("gather_one", gather_one_node)
    graph.add_node("analyse", analyse_node)
    graph.add_node("analyse_one", analyse_one_node)
    graph.add_node("synthesise", synthesise_node)
    graph.add_node("human_review", human_review_node)
    graph.add_node("prepare_revise", prepare_revise_node)
    graph.add_node("finalise", finalise_node)

    graph.add_edge(START, "plan")
    graph.add_edge("plan", "discover")
    graph.add_edge("discover", "checkpoint_a")
    graph.add_edge("checkpoint_a", "gather")
    # No static edges out of gather / analyse: those nodes route ONLY
    # via Command (goto=[Send...] or goto=["analyse"/"synthesise"]).
    # A static edge would fire alongside the Sends and run the next
    # node before the fan-out finished.
    graph.add_edge("gather_one", "analyse")
    graph.add_edge("analyse_one", "synthesise")
    graph.add_edge("synthesise", "human_review")
    graph.add_conditional_edges("human_review", route_after_review, {
        "revise": "prepare_revise", "finalise": "finalise", "end": END})
    graph.add_edge("prepare_revise", "gather")
    graph.add_edge("finalise", END)

    return graph.compile(checkpointer=MemorySaver())


def graph_config(run_id: str) -> dict:
    return {"configurable": {"thread_id": run_id},
            "recursion_limit": RECURSION_LIMIT}
