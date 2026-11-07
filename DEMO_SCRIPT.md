# Demo script — Enterprise Policy Q&A Bot (under 5 minutes)

Total target: ~4 minutes. Record the Streamlit app in the browser and the
CLI for one question. Speak plainly; show the app, not slides.

## 0:00–0:30 — What this is
"I built a RAG app that answers GitLab HR policy questions from the public
GitLab Handbook. It is the Week 2 project: pick a corpus, chunk it, embed
it, retrieve from it, and generate cited answers. My corpus is 29 People
Group handbook pages, about 87,000 words."

Show: the Streamlit sidebar (29 pages, source, stack) and `data/raw/`.

## 0:30–1:30 — Live question 1 (straightforward, with a number)
Ask: "How many paid sick days does GitLab give each team member?"
Point at: the answer — 25 paid sick days, rolling 12-month period — and the
`[1]` citation linking to the time-off-types handbook page. Then open the
"Retrieved passages" expander and show the exact passage the number came from.
Say: "Every factual claim has to cite a passage. If it cannot cite, it does
not say it."

## 1:30–2:30 — Live question 2 (ambiguous + multi-document)
Ask: "How much time off can I take?"
Point at: the answer distinguishing Flexible PTO from the 25 sick days and
the 16-week parental leave. Say: "Time off means three different policies
here. The bot names the readings instead of picking one silently."
Then ask: "Compare GitLab's parental leave with its sick leave."
Point at: sources from two different pages (leave-types and time-off-types)
in one answer.

## 2:30–3:30 — The honest part: what it refuses to answer
Ask: "What is the Wi-Fi password for the GitLab office in San Francisco?"
Point at: "Not in the knowledge base" — GitLab is all-remote, and there is
no such password in the handbook. Then ask the gym question ("Can I expense
a personal gym membership?") and show the same abstention.
Say: "For a policy bot, a wrong number is worse than no answer. Three of my
15 eval questions are unanswerable on purpose, to test exactly this."

## 3:30–4:00 — How it works + eval
Show the architecture diagram in the README for 20 seconds: scrape →
chunk 1200/200 → Gemini embeddings → local NumPy index → hybrid BM25 +
semantic, RRF fusion, LLM rerank → cited answer.
Then show `EVAL_REPORT.md`: 15 questions, retrieval hit rate, groundedness,
latency — including the failures. Say one line on the biggest failure and
what would fix it.
Close: "Code is on GitHub, the corpus manifest lists every source URL, and
the Pinecone backend is implemented as an option but the app runs without it."

## Shots to capture (for editing)
1. Streamlit app answering the sick-days question (citations visible).
2. "Retrieved passages" expander open.
3. The Wi-Fi abstention answer.
4. Terminal: `python -m scripts.ask "..."` returning a cited answer.
5. EVAL_REPORT.md summary table.
