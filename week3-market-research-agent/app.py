"""Streamlit demo for the Week 3 Market Research Agent.

Flow: enter a market -> the agent discovers the top 3 competitors
(Checkpoint A: approve or swap) -> gathers fresh data per competitor
in parallel -> extracts structured fields -> drafts the briefing
(Checkpoint B: approve, revise one competitor, or reject) -> final
briefing is written to data/briefings/ only after approval.

The agent never publishes, sends, or emails anything. Every claim in
the briefing cites a source URL from the run, or the field says
"not found in sources".
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from langgraph.types import Command  # noqa: E402

from src import llm, tavily_client  # noqa: E402
from src.graph import build_graph, graph_config  # noqa: E402
from src.state import initial_state, load_state, save_state  # noqa: E402

st.set_page_config(page_title="Market Research Agent — Week 3",
                   layout="wide")
st.title("🔍 Market Research Agent")
st.markdown(
    "A multi-agent researcher: it discovers the top 3 competitors in a "
    "market, gathers fresh web data for each one, extracts pricing, "
    "features, positioning and news, and drafts a cited briefing — "
    "pausing for a human at two checkpoints. Built with LangGraph, "
    "Tavily search, and OpenAI gpt-4o-mini.")

with st.sidebar:
    st.header("Knowledge base")
    st.write("**Source:** live web via Tavily Search + Extract")
    st.write("**Free tier:** 1,000 Tavily credits/month, no card")
    st.header("Stack")
    st.write("- Orchestration: LangGraph StateGraph, supervisor + workers")
    st.write("- Search: Tavily (basic depth, 1 credit per search)")
    st.write("- Generation: OpenAI `gpt-4o-mini`")
    st.write("- Fallback: Gemini `gemini-3-flash-preview`")
    st.write("- State: LangGraph MemorySaver + JSON run file")
    st.header("Guards")
    st.write("- 60 Tavily credits max per run (normal run: 20–30)")
    st.write("- Max 3 searches per competitor, recursion limit 25")
    st.write("- A field the sources do not answer says "
             "\"not found in sources\" — never invented")
    st.write("- Nothing is finalised until a human approves")


def _save_snapshot(graph, config) -> dict:
    """Write the durable JSON run file from the live graph state.

    Same snapshot the CLI runner takes after every node: credits from
    the Tavily counter, providers + OpenAI usage from the LLM module.
    Without this, a Streamlit-started run exists only in the in-memory
    checkpointer — no data/runs/<run_id>.json, no resume, no listing
    under Past runs."""
    state = dict(graph.get_state(config).values)
    state["credits_used"] = tavily_client.credits_used()
    state["providers_used"] = list(dict.fromkeys(llm.PROVIDERS_USED))
    state["llm_usage"] = llm.usage_totals()
    save_state(state)
    return state


def _invoke(graph, config, input_):
    """Run the graph until it pauses at an interrupt or finishes.
    Saves the JSON run file after every stream event, so a UI run
    persists exactly like a CLI run."""
    for _ in graph.stream(input_, config, stream_mode="updates"):
        _save_snapshot(graph, config)
    _save_snapshot(graph, config)
    return graph.get_state(config)


def _interrupt_payload(snapshot):
    for task in snapshot.tasks or []:
        for intr in task.interrupts or []:
            return intr.value
    return None


def _show_progress(state: dict) -> None:
    cols = st.columns(4)
    cols[0].metric("Status", state.get("status", "—"))
    cols[1].metric("Tavily credits", state.get("credits_used", 0))
    cols[2].metric("Competitors", len(state.get("competitors", [])))
    cols[3].metric("Sources found", len(state.get("sources", [])))
    errors = state.get("errors", [])
    if errors:
        with st.expander(f"Errors and retries ({len(errors)})"):
            for e in errors:
                st.write(f"- **{e['node']}**: {e['error']} "
                         f"— {e.get('resolution', '')}")


# ---------------------------------------------------------------- session
for key, default in [("graph", None), ("config", None), ("run_id", None),
                     ("stage", "idle"), ("market", "")]:
    if key not in st.session_state:
        st.session_state[key] = default

# ---------------------------------------------------------------- input
market = st.text_input(
    "Market to research",
    value="AI integration platforms (iPaaS)",
    placeholder="e.g. AI integration platforms (iPaaS)")
col_run, col_reset = st.columns([1, 1])
if col_run.button("▶ Start research run", type="primary"):
    st.session_state["graph"] = build_graph()
    state = initial_state(market)
    st.session_state["run_id"] = state["run_id"]
    st.session_state["config"] = graph_config(state["run_id"])
    st.session_state["market"] = market
    tavily_client.reset_credits()
    llm.reset_usage()
    with st.spinner("Discovering the top competitors…"):
        snap = _invoke(st.session_state["graph"], st.session_state["config"],
                       state)
    st.session_state["stage"] = "checkpoint_a"
    st.rerun()
if col_reset.button("Reset"):
    for key in ("graph", "config", "run_id", "stage"):
        st.session_state[key] = None if key != "stage" else "idle"
    st.rerun()

# ---------------------------------------------------------------- stages
if st.session_state["stage"] in ("checkpoint_a", "checkpoint_b", "done",
                                 "failed") and st.session_state["graph"]:
    graph = st.session_state["graph"]
    config = st.session_state["config"]
    snap = graph.get_state(config)
    state = dict(snap.values)
    _show_progress(state)

    if st.session_state["stage"] == "checkpoint_a":
        st.subheader("Checkpoint A — approve the competitors")
        st.write("The discovery agent proposed these 3 competitors. "
                 "Approve them, or swap one out before any deep research "
                 "is spent.")
        for c in state.get("competitors", []):
            st.write(f"- **{c['name']}** — {c.get('why', '')}")
        swap = st.text_input(
            "Swap (optional): three names, comma-separated",
            placeholder="e.g. Zapier, Make, n8n")
        if st.button("Approve competitors", type="primary"):
            decision: dict = {"decision": "approve"}
            if swap.strip():
                names = [n.strip() for n in swap.split(",") if n.strip()]
                if len(names) == 3:
                    decision = {"decision": "swap",
                                "competitors": [
                                    {"name": n, "why": "chosen by human"}
                                    for n in names]}
                else:
                    st.warning("A swap needs exactly 3 names — "
                               "approving the proposed list instead.")
            with st.spinner("Gathering data and drafting the briefing…"):
                _invoke(graph, config, Command(resume=decision))
            st.session_state["stage"] = "checkpoint_b"
            st.rerun()

    elif st.session_state["stage"] == "checkpoint_b":
        st.subheader("Checkpoint B — review the draft briefing")
        st.write("The graph is paused. Nothing is finalised until you "
                 "approve. You can also ask for one competitor to be "
                 "re-researched, or reject the draft.")
        draft = state.get("briefing_draft") or "*No draft yet.*"
        st.markdown(draft)
        revise_name = st.selectbox(
            "Re-research one competitor (optional)",
            [""] + [c["name"] for c in state.get("competitors", [])])
        c1, c2, c3 = st.columns(3)
        decision = None
        if c1.button("✅ Approve and finalise", type="primary"):
            decision = {"decision": "approve"}
        if c2.button("🔁 Revise one competitor") and revise_name:
            decision = {"decision": "revise", "competitor": revise_name}
        if c3.button("❌ Reject"):
            decision = {"decision": "reject"}
        if decision is not None:
            with st.spinner("Applying your decision…"):
                snap = _invoke(graph, config, Command(resume=decision))
            state = dict(snap.values)
            payload = _interrupt_payload(snap)
            if payload and payload.get("checkpoint") == "B":
                st.session_state["stage"] = "checkpoint_b"
            elif state.get("status") == "done":
                st.session_state["stage"] = "done"
            elif state.get("status") == "failed":
                st.session_state["stage"] = "failed"
            else:
                st.session_state["stage"] = "checkpoint_b"
            st.rerun()

    elif st.session_state["stage"] == "done":
        st.subheader("✅ Final briefing")
        run_id = st.session_state["run_id"]
        md_path = Path(f"data/briefings/final-{run_id}.md")
        if md_path.exists():
            st.markdown(md_path.read_text())
            st.download_button("Download briefing (Markdown)",
                               md_path.read_text(),
                               file_name=f"briefing-{run_id}.md")
        else:
            st.write("Final briefing file not found; see the run file.")
        st.write(f"Run file: `data/runs/{run_id}.json`")

    elif st.session_state["stage"] == "failed":
        st.subheader("Run ended without a final briefing")
        st.write("The human rejected the draft, or a node failed. "
                 "See the errors above and the run file for details.")
        st.write(f"Run file: `data/runs/{st.session_state['run_id']}.json`")

# ---------------------------------------------------------------- past runs
st.divider()
st.subheader("Past runs")
runs_dir = Path("data/runs")
if runs_dir.exists():
    for path in sorted(runs_dir.glob("*.json"), reverse=True)[:5]:
        try:
            data = load_state(path.stem)
            st.write(f"- `{path.stem}` — {data.get('market', '')} — "
                     f"{data.get('status', '')} — "
                     f"{data.get('credits_used', 0)} credits")
        except Exception:  # noqa: BLE001
            continue
