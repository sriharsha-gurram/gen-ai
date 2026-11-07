# Week 2 Project — Build Your RAG Application: Enterprise Policy Q&A Bot

**Author:** SriHarsha Gurram — Mastering Agentic AI, The Gen Academy, October 2026 cohort
**Repo:** (GitHub link added on submission)
**Track:** Code-heavy — Python, LangChain-style primitives implemented directly on the OpenAI API (first build ran on Gemini; switched Nov 7, 2026 — see Iterations)

## Project overview

My RAG app helps GitLab team members answer HR policy questions from the
GitLab Handbook (People Group sections) in a web app. Measured results
(Nov 7, 2026, EVAL_REPORT.md): 100% retrieval hit rate (12/12
answerable), 3/3 correct abstentions, 8/15 answers judged fully grounded
and 9/15 fact-correct, p95 latency 5.5s. The shortfall is depth, not
invention: multi-document and ambiguous answers state the core fact
correctly but omit secondary details.

New team members and managers constantly ask the same policy questions —
how much sick time do I get, how does parental leave work, who is my
onboarding buddy — and the answers live across dozens of handbook pages.
Keyword search returns whole pages; this bot returns a short, cited answer
built from the exact passages, and says "Not in the knowledge base" when
the handbook does not cover the question instead of inventing a policy.

## The RAG framework (Part 1)

- **User & decision:** GitLab team members (and their managers) deciding
  how to use a policy — taking time off, reporting an issue, planning a
  relocation. The decision is "what does the policy actually say, and what
  do I do next?"
- **Knowledge corpus:** The public GitLab Handbook, People Group / HR
  sections — 29 pages, 86,933 words, scraped Nov 7, 2026 (see
  `data/corpus_manifest.json` for every source URL). Format: handbook HTML
  cleaned to Markdown. Update cadence: the handbook changes often, so the
  corpus is a dated snapshot; refresh is one command (`src/scrape.py` +
  `src.ingest.py`).
- **Surface:** A Streamlit web app (`app.py`) plus a CLI (`scripts/ask.py`).
- **Faithfulness:** Every factual claim must cite a retrieved passage
  (`[1]`, `[2]` …). Measured in the eval by an LLM judge checking each
  claim against the retrieved passages: grounded / partial / ungrounded.
  Relevance alone is not enough — a true but off-policy sentence is a miss.
- **RAG mode:** One-shot retrieval per question (hybrid + rerank), with
  the answer generated once from the top-4 passages. No multi-hop needed:
  the multi-document questions are answered by retrieving across pages in
  a single pass.
- **Chunking + embedding:** 1200 characters per chunk with 200 characters
  of overlap, split on paragraph boundaries (never mid-paragraph when
  avoidable). Embedding model: OpenAI `text-embedding-3-small`
  (1536-dim). The first index used Gemini `gemini-embedding-2`
  (3072-dim); the Gemini free tier exhausted on Nov 7, 2026, so the
  index was re-embedded with OpenAI (605 chunks, 17 seconds, ~$0.003).
  The Gemini index is kept in `data/index/gemini-archive/`.
- **Retrieval:** Hybrid — semantic cosine search over OpenAI embeddings
  plus BM25 keyword search, fused with Reciprocal Rank Fusion, top-8
  candidates, then LLM reranking (gpt-4o-mini) to the top-4 passages
  used for generation.
- **Ingestion + freshness:** `src/scrape.py` fetches the 29 handbook pages
  (1s delay, no login) and writes `data/raw/*.md` + a manifest;
  `src/ingest.py` re-chunks and re-embeds everything. A refresh is a
  re-scrape plus a re-index; nothing is incremental yet.
- **What breaks first?** Long pages dilute the signal — the talent
  assessment page is ~85k characters, so a generic question can retrieve
  a plausible-sounding but wrong chunk. Ambiguous "time off" questions are
  the second failure mode: PTO, sick time, and parental leave are three
  different policies and the bot has to disambiguate before answering.
  The third is the free-tier embedding rate limit (429s) during indexing,
  handled with small batches and exponential backoff.
- **What would a 10/10 look like?** 95%+ grounded answers on answerable
  questions, correct abstention on all three unanswerable questions,
  retrieval hit rate above 90%, and p95 latency under 15 seconds.

## Dataset

GitLab Handbook, People Group sections (CC BY-SA 4.0), 29 pages, 86,933
words, 605 chunks. Examples: time-off-and-absence and its sub-pages
(leave-types, time-off-types, time-away-philosophy), general-onboarding,
onboarding-buddies, acceptable-use-policy, anti-harassment, promotions and
transfers, talent-assessment, relocation, visas, offboarding, all-remote.
Full list with URLs, character counts, and scrape date:
`data/corpus_manifest.json`. Deliberately NOT included: expenses,
compensation, and other handbook sections — the bot is honest about that
boundary (see the unanswerable eval questions).

## How it was built

1. **Scrape** the handbook with requests + BeautifulSoup, extracting the
   `<main>` content of each page and saving Markdown + manifest.
2. **Chunk** paragraph-aware (1200/200) — 605 chunks from 29 pages.
3. **Embed** with `text-embedding-3-small` via the batch API (100 per
   call). **Generate** with `gpt-4o-mini`. (First build used
   `gemini-embedding-2` + `gemini-3-flash-preview`; see Iterations.)
   Note: `gemini-2.5-flash` / `gemini-2.5-flash-lite` return 404 on this
   key as of Nov 7, 2026, so the verified working model is used instead.
4. **Store** vectors locally (NumPy `.npz` + JSON) — the default backend.
   A Pinecone backend is implemented as an optional drop-in
   (`PINECONE_API_KEY`), but the app runs end to end without it, and no
   Pinecone key is stored anywhere in the repo.
5. **Retrieve** hybrid BM25 + semantic with RRF fusion, then LLM rerank.
6. **Generate** cited answers with a strict grounding prompt and an
   explicit abstention path.
7. **Evaluate** with a 15-question set and an LLM judge (see EVAL_REPORT.md).

AI coding tools: the code was written with Muse (agentic coding) and
iterated against real runs — the 429 rate-limit failure during the first
ingest run is what produced the backoff logic, and manual testing of
unanswerable questions (asking for an office Wi-Fi password, a salary
band, a gym reimbursement) is what shaped the abstention wording. No
eval had run when this doc was first drafted. I did not look at the
course's provided solution folders.

## Prompts / agent instructions used

- **Answer prompt:** "Answer using ONLY the passages below… every factual
  claim must end with a citation… if the passages do not contain the
  answer, reply 'Not in the knowledge base…'". Full text in `src/qa.py`.
- **Rerank prompt:** score each passage 0–2 for relevance, return JSON
  only (`src/retrieve.py`).
- **Judge prompt:** groundedness (grounded / partial / ungrounded) and fact
  correctness (correct / partial / wrong) against the expected fact and the
  retrieved passages (`scripts/run_eval.py`).

## Iterations tried

1. Ingest kept failing on Gemini 429 rate limits: first at 50 chunks per
   batch with no backoff, then at 10 per batch. Fixes, in order: smaller
   batches with pauses and exponential backoff; resumable per-batch
   checkpoints so a failure resumes instead of restarting; switching the
   embedding model from `gemini-embedding-001` (quota exhausted Nov 7)
   to `gemini-embedding-2`; and larger chunks (1200 chars, 605 chunks
   instead of 971) to cut the number of embedding calls. A full ingest
   takes ~10-20 minutes at the free tier's pace and must run as a single
   process — a second concurrent ingest only burns quota faster.
2. First scrape attempt pulled in the handbook's global navigation (3,500+
   links). Restricted extraction to `<main>` and a curated page list plus
   one level of discovery from the time-off and onboarding hub pages.
3. Transient proxy timeouts dropped 4 handbook pages on the first pass
   (offboarding, onboarding-buddies, mr-buddies, tanewki-tips); retried
   them individually — all 4 recovered, taking the corpus from 25 to 29
   docs. The manifest's dropped list holds only gitlab.com edit/blob stub
   links, not handbook pages.
4. Reranking was added after manual testing showed that pure semantic
   top-4 sometimes surfaced a long generic page (talent-assessment) above
   the specific policy page; BM25 + RRF + LLM rerank fixed the worst of
   those. (This was observed in manual spot-checks, not in a formal eval
   run — the first full eval ran after this doc was drafted.)
5. Provider switch, Nov 7: the eval stalled after Q01 — Q02–Q10 all
   errored on Gemini 429s for both generation and embeddings, and the
   free-tier quota was fully exhausted. The user reloaded $5 of OpenAI
   API credit, so the pipeline switched to OpenAI end to end:
   `text-embedding-3-small` + `gpt-4o-mini`, via the stored
   `custom.openai` credential (same surrogate-helper pattern as the
   Gemini client, no raw key in the repo). The index was re-embedded
   (605 chunks, 17 seconds, ~$0.003) and the eval resumed for Q02–Q15,
   finishing in ~2.5 minutes for ~$0.008. Total OpenAI spend ~$0.011.
   Q01 is kept from the Gemini run and is labelled as such in
   EVAL_REPORT.md. The Gemini index is archived under
   `data/index/gemini-archive/`.

## Evaluation

15 questions: 6 straightforward, 2 ambiguous, 3 multi-document,
3 unanswerable, 1 edge case. Full per-question results, scores, and
failure analysis: `EVAL_REPORT.md`.

Measured (Nov 7, 2026, 15 questions): retrieval hit rate 12/12 (100%),
correct abstention 3/3, grounded 8/15, fact correct 9/15, latency mean
7.0s / p95 5.5s (OpenAI questions 3–6s; Q01 ran on Gemini at 45.9s).
Total OpenAI cost for the re-embed + full eval: ~$0.011 of the $5.00
credit. The judge's "partial" marks are all depth gaps (a correct core
fact missing secondary details), never invented facts. Full detail:
`EVAL_REPORT.md`.

## Learnings and observations

- Most RAG failures are retrieval failures, not generation failures — the
  handout's warning held up exactly. The model rarely invents when the
  passages are right; it invents when the passages are wrong or missing.
- The abstention path is the highest-value feature for a policy bot. A
  wrong policy number is worse than no answer, so the eval's unanswerable
  questions are the ones I care most about passing.
- A local vector store is enough at this scale (605 chunks). Pinecone
  would matter at thousands of documents or for shared/team use, not for
  correctness here — so it is an optional backend, not a dependency.
- Free-tier rate limits are a real engineering constraint, not a footnote:
  they shaped the batching, the sleeps, and the backoff code.
