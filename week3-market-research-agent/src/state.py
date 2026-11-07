"""Shared graph state and per-run JSON persistence.

The LangGraph checkpointer (MemorySaver) holds state while a run is
alive. The JSON run file under ``data/runs/<run_id>.json`` is the
durable copy, written after every node: on restart the run resumes
from this file and never re-searches a competitor whose findings are
already saved.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langgraph.graph import MessagesState  # noqa: F401  (kept for clarity)

RUNS_DIR = Path(__file__).resolve().parent.parent / "data" / "runs"
BRIEFINGS_DIR = Path(__file__).resolve().parent.parent / "data" / "briefings"

CREDIT_GUARD = 60          # stop and ask the human above this many Tavily credits
MAX_SEARCHES_PER_COMPETITOR = 3
MAX_ANALYST_PASSES = 2
RECURSION_LIMIT = 25


def _merge_dicts(a: dict, b: dict) -> dict:
    merged = dict(a or {})
    for k, v in (b or {}).items():
        if v is None:
            merged.pop(k, None)  # None deletes the key (revise path)
        else:
            merged[k] = v
    return merged


def _merge_lists(a: list, b: list) -> list:
    return list(a or []) + list(b or [])


class AgentState(TypedDict, total=False):
    market: str
    run_id: str
    competitors: Annotated[list[dict], _merge_lists]  # name, why, status
    findings: Annotated[dict[str, list[dict]], _merge_dicts]  # per competitor
    extracted: Annotated[dict[str, dict], _merge_dicts]  # per competitor
    briefing_draft: str | None
    sources: Annotated[list[str], _merge_lists]  # every cited URL, deduped later
    status: str  # planned/discovering/gathering/analysing/drafting/awaiting_human/done/failed
    errors: Annotated[list[dict], _merge_lists]  # node, error, retry, resolution
    iterations: int
    analyst_passes: int
    human_decision: str | None  # approved / revise / rejected
    human_notes: str
    revise_competitor: str | None
    checkpoint_a_done: bool
    checkpoint_b_done: bool
    competitor: str  # transient: set by Send fan-out for gather_one/analyse_one
    my_findings: list[dict]  # transient: Send payload for analyse_one
    credits_used: int
    providers_used: Annotated[list[str], _merge_lists]
    llm_usage: dict  # per-model tokens + estimated cost (OpenAI only)
    started_at: str
    finished_at: str | None
    timings: Annotated[dict[str, float], _merge_dicts]  # node -> seconds


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] or "market"


def new_run_id(market: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{slugify(market)}-{stamp}"


def initial_state(market: str, run_id: str | None = None) -> AgentState:
    return AgentState(
        market=market,
        run_id=run_id or new_run_id(market),
        competitors=[],
        findings={},
        extracted={},
        briefing_draft=None,
        sources=[],
        status="planned",
        errors=[],
        iterations=0,
        analyst_passes=0,
        human_decision=None,
        human_notes="",
        revise_competitor=None,
        checkpoint_a_done=False,
        checkpoint_b_done=False,
        credits_used=0,
        providers_used=[],
        started_at=datetime.now(timezone.utc).isoformat(),
        finished_at=None,
        timings={},
    )


def run_path(run_id: str) -> Path:
    return RUNS_DIR / f"{run_id}.json"


def save_state(state: dict) -> Path:
    """Write the durable JSON run file (atomic replace)."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    path = run_path(state["run_id"])
    tmp = path.with_suffix(".tmp")
    serialisable = {k: v for k, v in state.items()
                    if k not in ("messages", "competitor", "my_findings")}
    tmp.write_text(json.dumps(serialisable, indent=2, default=str))
    tmp.replace(path)
    return path


def load_state(run_id: str) -> dict:
    path = run_path(run_id)
    if not path.exists():
        raise FileNotFoundError(f"No saved run {run_id} at {path}")
    return json.loads(path.read_text())


def list_runs() -> list[str]:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(p.stem for p in RUNS_DIR.glob("*.json"))


def dedupe_sources(state: dict) -> list[str]:
    seen: list[str] = []
    for url in state.get("sources", []):
        if url and url not in seen:
            seen.append(url)
    return seen
