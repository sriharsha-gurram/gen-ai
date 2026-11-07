"""The agent's 5 tools. Read vs write is marked on each one.

1. tavily_search(query, max_results) — read
2. tavily_extract(urls) — read
3. list_sources(state) — read
4. save_briefing_draft(state, markdown) — write, local file only
5. request_human_review(state, summary) — write/handoff; pauses the graph

Deliberately not included: no send/post/publish tool, no email tool,
no tool that spends money. The agent cannot publish anything on its own.
"""
from __future__ import annotations

from pathlib import Path

from src import tavily_client
from src.state import BRIEFINGS_DIR, dedupe_sources

TOOL_CATALOG = [
    {"name": "tavily_search", "kind": "read",
     "desc": "Tavily Search API, basic depth, 1 credit per call."},
    {"name": "tavily_extract", "kind": "read",
     "desc": "Tavily Extract API, returns page text, 1 credit per 5 URLs."},
    {"name": "list_sources", "kind": "read",
     "desc": "Deduplicated source list from state, for coverage checks."},
    {"name": "save_briefing_draft", "kind": "write",
     "desc": "Writes a draft briefing to data/briefings/ (local file only)."},
    {"name": "request_human_review", "kind": "write/handoff",
     "desc": "Pauses the graph at a human checkpoint with the draft "
             "and open questions. The only path to a final briefing."},
]


def tavily_search(query: str, max_results: int = 5) -> list[dict]:
    """Tool 1 (read): web search. Raises TavilyError after retries."""
    return tavily_client.search(query, max_results=max_results, depth="basic")


def tavily_extract(urls: list[str]) -> tuple[list[dict], list[str]]:
    """Tool 2 (read): extract page text. Returns (extracted, failed_urls).
    A failed URL is reported, never silently replaced with a snippet."""
    got = tavily_client.extract(urls)
    got_urls = {item["url"] for item in got}
    failed = [u for u in urls if u not in got_urls]
    return got, failed


def list_sources(state: dict) -> list[str]:
    """Tool 3 (read): every source URL cited so far, deduplicated."""
    return dedupe_sources(state)


def save_briefing_draft(state: dict, markdown: str) -> Path:
    """Tool 4 (write, local file only): save the draft briefing."""
    BRIEFINGS_DIR.mkdir(parents=True, exist_ok=True)
    path = BRIEFINGS_DIR / f"draft-{state['run_id']}.md"
    path.write_text(markdown)
    return path


def request_human_review(state: dict, summary: str) -> dict:
    """Tool 5 (write/handoff): record that the graph paused for a human.

    The actual pause is enforced by LangGraph's interrupt() in the
    graph node; this tool is the audit record of the handoff. It
    returns the payload the human sees."""
    return {
        "run_id": state["run_id"],
        "market": state["market"],
        "status": state["status"],
        "summary": summary,
        "competitors": [c["name"] for c in state.get("competitors", [])],
        "credits_used": state.get("credits_used", 0),
        "open_questions": state.get("human_notes", ""),
    }
