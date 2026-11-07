"""Run the Week 3 Market Research Agent from the CLI.

Usage:
  python -m scripts.run_agent "AI integration platforms (iPaaS)"
  python -m scripts.run_agent "vector databases" --auto-approve
  python -m scripts.run_agent --resume <run_id> [--auto-approve]

The run pauses at two human checkpoints (A: competitor list, B: draft
briefing). With --auto-approve both are approved automatically (used
by the eval). Without it, the CLI prompts. After every node the state
is saved to data/runs/<run_id>.json, so a killed run resumes with
--resume and never re-searches a competitor whose findings are saved.
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from langgraph.types import Command

sys.path.insert(0, str(__file__).rsplit("/scripts/", 1)[0])

from src import llm, tavily_client  # noqa: E402
from src.graph import build_graph, graph_config  # noqa: E402
from src.state import (initial_state, list_runs, load_state,  # noqa: E402
                       save_state)


def _save_snapshot(graph, config, run_id: str) -> dict:
    state = graph.get_state(config).values
    state = dict(state)
    state["credits_used"] = tavily_client.credits_used()
    # Parallel nodes do not report providers (merge hazard); the router
    # module is the single source of truth.
    from src import llm
    state["providers_used"] = list(dict.fromkeys(llm.PROVIDERS_USED))
    state["llm_usage"] = llm.usage_totals()
    save_state(state)
    return state


def _pending_interrupt(graph, config):
    snap = graph.get_state(config)
    for task in snap.tasks or []:
        for intr in task.interrupts or []:
            return intr.value
    return None


def _ask_checkpoint(payload: dict, auto: bool) -> dict:
    checkpoint = payload.get("checkpoint", "?")
    print(f"\n=== Human checkpoint {checkpoint} ===")
    if checkpoint == "A":
        print("Proposed competitors:")
        for c in payload.get("competitors", []):
            print(f"  - {c['name']}: {c.get('why', '')}")
        print(f"Tavily credits used so far: {payload.get('credits_used', 0)}")
        if auto:
            print("auto-approve: approving")
            return {"decision": "approve"}
        print("Approve? [Enter] approve / type a replacement list as "
              "'Name1, Name2, Name3' to swap all three")
        answer = input("> ").strip()
        if not answer:
            return {"decision": "approve"}
        names = [n.strip() for n in answer.split(",") if n.strip()]
        if len(names) == 3:
            return {"decision": "swap",
                    "competitors": [{"name": n, "why": "chosen by human"}
                                    for n in names]}
        print("Need exactly 3 names; approving the proposed list.")
        return {"decision": "approve"}
    # Checkpoint B
    print("Draft briefing ready.")
    print(f"Tavily credits used so far: {payload.get('credits_used', 0)}")
    if auto:
        print("auto-approve: approving")
        return {"decision": "approve"}
    print("Approve? [Enter] approve / 'revise <Competitor>' to re-research "
          "one competitor / 'reject' to stop with no final briefing")
    answer = input("> ").strip()
    if not answer:
        return {"decision": "approve"}
    if answer.lower().startswith("revise "):
        return {"decision": "revise",
                "competitor": answer[7:].strip()}
    if answer.lower() == "reject":
        return {"decision": "reject"}
    return {"decision": "approve"}


def run(market: str | None, run_id: str | None = None,
        auto: bool = False) -> dict:
    graph = build_graph()
    if run_id:
        state = load_state(run_id)
        market = state["market"]
        print(f"Resuming run {run_id} for market: {market}")
    else:
        state = initial_state(market)
        run_id = state["run_id"]
        print(f"Starting run {run_id} for market: {market}")
    tavily_client.reset_credits()
    llm.reset_usage()
    # On resume, restore the credit counter from the saved state so the
    # guard sees the true total (credits are not re-counted on replay).
    tavily_client._CREDITS = int(state.get("credits_used", 0))
    config = graph_config(run_id)
    t0 = time.time()
    current_input: object = state
    while True:
        for _event in graph.stream(current_input, config,
                                   stream_mode="updates"):
            _save_snapshot(graph, config, run_id)
        state = _save_snapshot(graph, config, run_id)
        payload = _pending_interrupt(graph, config)
        if payload is None:
            break
        decision = _ask_checkpoint(payload, auto)
        current_input = Command(resume=decision)
    elapsed = round(time.time() - t0, 1)
    state["credits_used"] = tavily_client.credits_used()
    save_state(state)
    print(f"\nRun {run_id} finished in {elapsed}s "
          f"(status: {state.get('status')}, "
          f"Tavily credits: {state['credits_used']})")
    print(f"Run file: data/runs/{run_id}.json")
    if state.get("status") == "done":
        print(f"Final briefing: data/briefings/final-{run_id}.md")
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the market research agent.")
    parser.add_argument("market", nargs="?", help="Market to research")
    parser.add_argument("--resume", help="Resume a saved run by run id")
    parser.add_argument("--auto-approve", action="store_true",
                        help="Approve both human checkpoints automatically")
    parser.add_argument("--list-runs", action="store_true")
    args = parser.parse_args()
    if args.list_runs:
        for r in list_runs():
            print(r)
        return 0
    if args.resume:
        run(None, run_id=args.resume, auto=args.auto_approve)
        return 0
    if not args.market:
        parser.error("give a market, or --resume <run_id>")
    run(args.market, auto=args.auto_approve)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
