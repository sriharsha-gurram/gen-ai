# Week 3 Project — Build Your AI Agent: Market Research Agent

**Author:** SriHarsha Gurram — Mastering Agentic AI, The Gen Academy, October 2026 cohort
**Use case:** 3A Market Research Agent (competitor analysis)
**Track:** Code-heavy — Python, LangGraph StateGraph, Tavily, OpenAI

## What it is

A multi-agent researcher that takes one line — a market name, e.g.
"AI integration platforms (iPaaS)" — and produces a cited
3-competitor briefing in under 15 minutes. Three specialist agents
plus an orchestrator, coordinated by a LangGraph supervisor:

1. **Competitor Discovery** — Tavily search finds the top 3 vendors.
2. **Data Gathering** — per competitor, in parallel: pricing, features,
   and recent-news searches plus page extracts.
3. **Analyst / Extractor** — structured fields (pricing model, starting
   price, core features, positioning, recent news) from the gathered
   pages only. A field the sources do not answer is recorded as
   "not found in sources" — never invented.
4. **Orchestrator** — compiles the briefing: per-competitor pages,
   comparison table, what-to-watch note, source list.

Two human checkpoints are enforced by the graph (`interrupt()`), not
by convention: after discovery (approve or swap a competitor) and
after the draft briefing (approve, re-research one competitor, or
reject). Nothing is written to `data/briefings/final-*` until a human
approves. The agent cannot publish, send, or email anything.

## Measured results (Nov 7, 2026, EVAL_REPORT.md)

- **Groundedness:** 0.90 iPaaS (9/10 claims grounded, 1 partial, 0 ungrounded), 1.00 vector DBs (10/10) — target was 90%+.
- **Completeness:** 12/15 fields in both markets; recent news is the gap for all six competitors (dates rarely visible in sources).
- **Citation coverage:** 14/14 (iPaaS), 8/8 (vector DBs) point at run sources.
- **URLs live-checked:** 6/6 (iPaaS), 5/6 (vector DBs).
- **Cost per run:** 14 Tavily credits, 0 errors, under 1 minute end to end.

Full per-claim judgements are in `EVAL_REPORT.md`. The vector-database market the agent discovered was Pinecone, Milvus, and Weaviate (not Qdrant — the live search ranked Milvus above it).

## How it works

- **Orchestration:** LangGraph `StateGraph`, supervisor with workers
  as tools. `plan → discover → checkpoint A → gather (Send fan-out) →
  analyse (Send fan-out) → synthesise → human review → finalise`.
  `MemorySaver` checkpointer plus a JSON run file after every node.
- **Tools (5):** `tavily_search` (read), `tavily_extract` (read),
  `list_sources` (read), `save_briefing_draft` (write, local file
  only), `request_human_review` (handoff).
- **Search:** Tavily basic depth, 1 credit per search, 1 credit per
  5 extracted URLs. Normal run: ~20–30 credits of the free 1,000/month.
  Hard guard at 60 credits per run.
- **Generation:** OpenAI `gpt-4o-mini` (primary). Gemini
  `gemini-3-flash-preview` is the fallback if OpenAI fails. No Nebius
  call: the handout asks for at least one Nebius Token Factory call,
  but Nebius is blocked at Google sign-in recovery, so the write-up
  documents the substitution honestly instead of faking it.
- **State and resume:** `AgentState` (market, competitors, findings,
  extractions, draft, sources, errors, credits, human decisions) is
  checkpointed in memory and saved to `data/runs/<run_id>.json` after
  every node. Restarting with `--resume <run_id>` re-runs the graph
  from the start, but every node skips work already saved — a resumed
  run never re-searches a completed competitor.
- **Guards:** recursion limit 25, max 3 searches per competitor, max 2
  analyst passes, credit guard 60. The analyser's starting-price
  digits must appear in a gathered source, or the field is dropped
  to "not found in sources".

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Interactive (prompts at both checkpoints)
python -m scripts.run_agent "AI integration platforms (iPaaS)"

# Auto-approve both checkpoints (eval mode)
python -m scripts.run_agent "vector databases" --auto-approve

# Resume a killed run from its JSON file (no re-search of saved work)
python -m scripts.run_agent --resume <run_id> --auto-approve

# Evaluate both markets and write EVAL_REPORT.md
python -m scripts.run_eval

# Demo UI
streamlit run app.py
```

Credentials come from Muse's secure store (`custom.openai`,
`custom.gemini`, `custom.tavily`) via the surrogate helper — no key
is read, printed, or stored in this repo. Outside Muse, set the keys
in a local `.env` (see `.env.example`); `.env` is gitignored.

## Project layout

```
app.py                  Streamlit demo (market input, checkpoints, briefing)
src/
  graph.py              LangGraph StateGraph, nodes, guards, interrupts
  state.py              AgentState + JSON run persistence
  tools.py              The 5 tools (read vs write marked)
  tavily_client.py      Tavily search/extract, credit counter, retry
  llm.py                OpenAI primary, Gemini fallback router
  openai_client.py      Stored-credential OpenAI client (Week 2 pattern)
  gemini_client.py      Stored-credential Gemini client (fallback)
  briefing.py           Deterministic briefing rendering
scripts/
  run_agent.py          CLI runner (interactive / auto / resume)
  run_eval.py           Two-market eval + EVAL_REPORT.md
data/
  runs/                 JSON run files (gitignored)
  briefings/            Draft + final briefings (gitignored, except samples/)
```

## What it never does

- Never invents pricing, features, or news. Every claim cites a
  source URL from the run, or is labelled analyst inference.
- Never publishes, sends, posts, or emails a briefing without human
  approval.
- Never uses employer internal data (no Harvey systems, no work Jira).
- Never spends money: free tiers only, no paid plan, no card.
