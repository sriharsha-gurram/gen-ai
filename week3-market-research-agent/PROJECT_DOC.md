# Week 3 Project — Build Your AI Agent: Market Research Agent

**Author:** SriHarsha Gurram — Mastering Agentic AI, The Gen Academy, October 2026 cohort
**Use case:** 3A Market Research Agent (competitor analysis)
**Repo:** https://github.com/sriharsha-gurram/gen-ai
**Track:** Code-heavy — Python, LangGraph, Tavily, OpenAI

## Project overview

My agent helps a product manager research a new market in a web app,
replacing 6 hours of manual googling with a cited 3-competitor
briefing in under 15 minutes. It searches the web, pulls each
competitor's pricing and positioning, and drafts a one-page brief on
its own using 5 tools, hands off to a human to review before the
brief gets saved, and I know it works when a PM can get a usable
market brief in under 15 minutes that they would actually send to
their team 8 times out of 10.

Default market: AI integration platforms (iPaaS) — Workato, Boomi,
MuleSoft. I work in integrations, so I can judge whether a pricing or
feature claim about these vendors is true. Second eval market: vector
databases — Pinecone, Weaviate, Qdrant (as planned; the live runs
discovered Milvus instead of Qdrant — see Measured results) — to
prove the agent is not
hard-coded to one market.

Measured results (Nov 7, 2026, EVAL_REPORT.md): groundedness 0.90
(iPaaS: 9 of 10 sampled claims grounded, 1 partial, 0 ungrounded) and
1.00 (vector DBs: 10 of 10 grounded) — both at or above the 90%
target. Completeness 12/15 fields in both markets (pricing, features,
positioning present for every competitor; recent news missing for all
six — dates are rarely visible in the sources, so the extractor
leaves it out rather than guessing). Citation coverage 14/14 (iPaaS)
and 8/8 (vector DBs) point at run sources. URLs live-checked 6/6
(iPaaS) and 5/6 (vector DBs). Each run: 14 Tavily credits, 0 errors,
under 1 minute end to end.

## The agent framework (Part 2 of the handout)

- **Agent goal (one line):** "My agent helps a product manager
  research a new market in a web app, replacing 6 hours of manual
  googling with a cited 3-competitor briefing in under 15 minutes."
- **Where do people use it?** Web app (Streamlit), run on demand.
  No Slack, no email, no auto-trigger.
- **What steps does it take, in order?** Plan, discover the top 3
  competitors, gather fresh data per competitor in parallel, extract
  structured fields, synthesise a draft briefing, pause for human
  review, finalise on approval.
- **What can it actually do?** 5 tools: Tavily search (read), Tavily
  extract (read), list sources (read), save draft briefing (write,
  local file only), request human review (handoff). Read-only except
  the local draft save and the handoff.
- **What does it need to remember?** Competitor list, findings with
  source URLs and dates, extractions and what was not found, errors
  and retries, human decisions. Stored in LangGraph state plus a JSON
  run file; resumes from the file on restart.
- **What should it never do?** Never invent pricing, features, or
  news; never publish or send anything without approval; never use
  employer internal data; never spend money or exceed the Tavily free
  quota.
- **Human-in-the-loop:** after competitor discovery (swap a
  competitor) and after the draft briefing (approve, revise one
  competitor, or reject). Both are graph interrupts, not suggestions.
- **What happens when something breaks?** Tavily failure: backoff,
  retry 3 times, then mark "insufficient data" and continue. LLM
  failure: retry once, then the supervisor decides. Loop: hard caps
  route to human review with partial state.
- **How do you know it worked?** A usable cited briefing for 3
  competitors in under 15 minutes that a PM would actually take into
  a meeting, 8 times out of 10 runs. Groundedness target 90%+ of
  claims cited.

## Dataset

There is no fixed corpus: the data is the live web, fetched fresh per
run through Tavily. Every finding carries its source URL, title,
snippet, and (where extracted) page text. The briefing's Sources
section lists every URL the run cited. The two eval markets are
iPaaS (Workato, Boomi, MuleSoft) and vector databases (Pinecone,
Weaviate, Qdrant as planned — the live runs discovered Milvus
instead of Qdrant). Deliberately NOT included: employer internal data,
work Jira, internal docs — the agent only ever reads the public web.

## How it was built

1. **Tavily client** (`src/tavily_client.py`): search + extract with
   the stored `custom.tavily` credential via the surrogate helper,
   a running credit counter, and exponential backoff on 429/5xx.
2. **LLM router** (`src/llm.py`): OpenAI `gpt-4o-mini` primary via the
   stored `custom.openai` credential; Gemini `gemini-3-flash-preview`
   fallback only. Both clients are copied from the Week 2 pattern
   (surrogate helper, no raw key in code).
3. **Graph** (`src/graph.py`): LangGraph `StateGraph`, supervisor with
   workers as tools, `Send` fan-out for per-competitor gather and
   analyse, `MemorySaver` checkpointer, `interrupt()` at both human
   checkpoints, hard caps (recursion 25, 3 searches per competitor,
   2 analyst passes, 60-credit guard).
4. **State + persistence** (`src/state.py`): `AgentState` TypedDict
   with merge reducers for parallel fan-in, plus a JSON run file
   written after every node.
5. **Briefing** (`src/briefing.py`): the comparison table is rendered
   deterministically from extracted fields, so the table cannot invent
   a value; the LLM writes only the narrative, with citations.
6. **UI** (`app.py`): Streamlit — market input, progress by node,
   checkpoint A (approve/swap), draft view, checkpoint B
   (approve/revise/reject), final briefing.
7. **Eval** (`scripts/run_eval.py`): runs both markets, judges sampled
   claims against their cited source text, checks completeness and
   citation coverage, writes `EVAL_REPORT.md`.

AI coding tools: the code was written with Muse (agentic coding) and
iterated against real runs — the first end-to-end run exposed the
LangGraph 1.x `Send` return-value change, which the fix (returning
`Command(goto=[Send(...)])`) addressed. I did not look at the course's
provided solution folders.

## Prompts / agent instructions used

- **Discovery prompt:** rank the top 3 competitors from search results,
  one line each on why they qualify; do not invent vendors not in the
  results (`src/graph.py`, discover node).
- **Analyst prompt:** extract structured fields from the gathered
  sources ONLY; a missing field is exactly "not found in sources";
  never guess a price; recent news only if dated in the last 90 days
  (`src/graph.py`, analyse node). A code-level guard drops a starting
  price whose digits do not appear in any gathered source.
- **Synthesis prompt:** write per-competitor narrative + what-to-watch
  from the extracted facts only, every factual sentence ending with a
  [n] citation to the numbered source list; inference marked as
  "(analyst inference)" (`src/graph.py`, synthesise node).
- **Judge prompt (eval):** grounded / partial / ungrounded for each
  sampled claim against its cited source text (`scripts/run_eval.py`).

## Iterations tried

1. **LangGraph `Send` return value:** the first end-to-end run failed
   after checkpoint A with `InvalidUpdateError: Expected dict, got
   [Send(...)]`. LangGraph 1.x requires fan-out nodes to return
   `Command(goto=[Send(...)])`, not a bare list. Fixed in both the
   gather and analyse fan-out nodes; the run then resumed from its
   saved JSON file and completed without re-searching anything.
2. **Resume path:** the same failed run proved the resume design — the
   run file saved after checkpoint A held the approved competitor
   list, and `--resume` picked it up with no re-search (2 credits
   stayed spent, not re-billed).
3. **Discovery quality:** the first discovery pass proposed MuleSoft,
   Boomi, Workato for iPaaS — the right three — from two plain
   searches, so no query tuning was needed.
4. **Eval fix — citations that did not support their claims:** the
   first full eval scored groundedness 0.0 (iPaaS) and 0.125 (vector
   DBs). The briefings were not inventing facts — the synthesis step
   was citing plausible-looking sources that did not actually state
   the sentence. Two fixes: (a) the synthesis prompt now gets a
   per-competitor source map and may only cite that competitor's own
   sources, dropping a sentence it cannot support; (b) the eval judge
   now checks a claim against ALL its cited sources together (snippet
   + extracted text) instead of only the first citation, and skips
   honest "not found" absence statements. The eval was re-run after
   the fix; see EVAL_REPORT.md for the new numbers.
5. **Eval fix 2 — per-field sources:** the re-run improved
   groundedness to 0.6 (iPaaS) and 0.333 (vector DBs) but the
   synthesis still blended facts into marketing-style sentences no
   single source states. The fix is structural: the extractor now
   returns every field as {value, source}, the normaliser drops any
   value whose source is not a gathered URL, the comparison table
   reads the new shape, and the synthesis prompt gets a per-fact
   source map with instructions to write short atomic sentences, one
   fact each, citing exactly that fact's number. The eval was re-run
   after this fix; see EVAL_REPORT.md. Final numbers after the fix:
   groundedness 0.90 (iPaaS) and 1.00 (vector DBs), both at or above
   the 90% target; the one iPaaS partial was a Boomi $99/month
   phrasing the cited page states differently.

## Evaluation

Two markets, auto-approved checkpoints, scored per briefing on
groundedness (sampled claims vs cited source text), completeness
(pricing, features, positioning, news per competitor), citation
coverage (citations pointing at run sources + live URL checks), time,
and Tavily credits. Full per-market numbers and per-claim judgements:
`EVAL_REPORT.md`.

## Learnings and observations

- Most agent failures are control-flow failures, not model failures:
  the first real bug was a framework API change in how fan-out is
  returned, not a bad answer.
- The "not found in sources" path is the highest-value feature of a
  research agent. Pricing pages are often paywalled or
  JavaScript-rendered, and a missing price stated plainly is a correct
  answer; an invented price is a failure.
- A credit counter in state turns a runaway loop from a billing risk
  into a visible number. The guard never fired in the eval runs, but
  knowing it is there is what makes the demo safe to run live.
- The handout asks for at least one Nebius Token Factory call. Nebius
  is blocked at Google sign-in recovery, so this build uses OpenAI
  instead and says so here plainly rather than pretending otherwise.
  The substitution changes nothing about the agent's behaviour — the
  model is one interchangeable call behind the `src/llm.py` router.
- Mem0 long-term memory was deliberately not used: a single-run
  research agent does not need cross-session user memory, and bolting
  it on would be decoration.
