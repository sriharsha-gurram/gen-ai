# Demo script — Market Research Agent (under 5 minutes)

Total target: ~4 minutes. Record the Streamlit app in the browser and
the CLI for one command. Speak plainly; show the agent working, not slides.

## 0:00–0:30 — What this is
"I built a multi-agent market research system. Give it a market, and
it discovers the top 3 competitors, gathers fresh web data for each
one, extracts pricing, features and news, and drafts a cited
briefing — pausing for a human twice before anything is final."

Show: the Streamlit sidebar (5 tools, guards) and the market input
with "AI integration platforms (iPaaS)".

## 0:30–1:15 — Checkpoint A: the human approves the competitors
Click "Start research run". Point at: the discovery agent proposed
MuleSoft, Boomi, Workato. Say: "The agent picked the three vendors
itself from live search. I can swap one out here before it spends any
research credits — or just approve."
Click "Approve competitors".

## 1:15–2:30 — The work happens: gather + extract
While it runs, point at the progress: credits ticking up, sources
found, per-competitor findings. Say: "Three gather agents run in
parallel, one per competitor — pricing, features, and news searches,
then page extracts. The analyst then pulls structured fields out of
those pages only. If a price is not in the sources, the field says
'not found in sources' instead of guessing."

## 2:30–3:30 — Checkpoint B: the draft and the decision
Show the draft briefing: per-competitor pages, the comparison table,
the sources list. Point at one cited price and its [n] link. Say:
"Nothing is final until I approve this draft. I could also send one
competitor back for a re-run, or reject it."
Click "Approve and finalise". Show the final briefing file and the
run file.

## 3:30–4:00 — How it works + eval
Show the README architecture line for 20 seconds: supervisor +
3 workers, 5 tools, 2 human interrupts, JSON resume. Then show
`EVAL_REPORT.md`: two markets, groundedness, credits used.
Close: "Code is on GitHub, the Nebius call in the handout is
documented as substituted with OpenAI because Nebius sign-in is
blocked, and every claim in the briefing traces to a source URL."

## Shots to capture (for editing)
1. Streamlit app with the market input and sidebar guards.
2. Checkpoint A: the 3 proposed competitors.
3. The draft briefing with citations visible.
4. Checkpoint B approval and the final briefing file.
5. EVAL_REPORT.md summary table.
