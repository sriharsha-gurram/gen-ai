# Week 2 Project — Build Your RAG Application

**Enterprise Policy Q&A Bot** — a RAG application over the public GitLab
Handbook (People Group / HR policy sections). Ask a question about GitLab HR
policies and get a cited answer drawn only from the handbook. If the answer
is not in the handbook, the bot says so instead of guessing.

Course: Mastering Agentic AI, The Gen Academy (Maven, Oct–Nov 2026 cohort).
Week 2 topic: Grounding AI with RAG & Context Engineering. Track: code-heavy
(Python, LangChain-style primitives — implemented directly on the OpenAI API
so the pipeline is visible end to end; no framework magic hiding the
chunking, retrieval, or reranking steps. The first build ran on Gemini;
see the provider note under Architecture.)

## The one-liner

> My RAG app helps GitLab team members answer HR policy questions from the
> GitLab Handbook (People Group sections) in a web app. Measured results
> (Nov 7, 2026, EVAL_REPORT.md): 100% retrieval hit rate (12/12
> answerable), 3/3 correct abstentions, 8/15 answers judged fully
> grounded and 9/15 fact-correct by the LLM judge — the shortfall is
> depth, not invention: multi-document and ambiguous answers state the
> core fact correctly but omit secondary details. Latency p95 5.5s
> (OpenAI questions 3–6s; Q01 ran on Gemini at 45.9s).

## Corpus

- **Source:** GitLab Handbook, https://handbook.gitlab.com — People Group /
  HR sections. Public website, published under CC BY-SA 4.0.
- **29 documents, 86,933 words**, scraped Nov 7, 2026 with
  `src/scrape.py` (requests + BeautifulSoup, 1s delay, no login).
  Full manifest with exact URLs: `data/corpus_manifest.json`.
- **605 chunks** (1200 chars, 200-char overlap, paragraph-aware).
- Topics: time off and leave (Flexible PTO, 25 sick days, 16-week parental
  leave), onboarding and onboarding buddies, acceptable use, anti-harassment,
  learning and development, promotions, talent assessment, 360 feedback,
  relocation, visas, offboarding, remote work, and more.
- Raw sources live in `data/raw/` (one Markdown file per handbook page).

## Architecture

```
GitLab Handbook pages
  -> src/scrape.py            (fetch + clean, data/raw/*.md + manifest)
  -> src/ingest.py            (chunk 1200/200, batch-embed, build index)
  -> data/index/              (chunks.json + vectors.npz, local NumPy store)
  -> src/retrieve.py          (hybrid: BM25 keyword + semantic, RRF fusion,
                               LLM rerank of top-8 -> top-4)
  -> src/qa.py                (cited answer from retrieved passages only;
                               abstains with "Not in the knowledge base")
  -> app.py (Streamlit) / scripts/ask.py (CLI)
```

- **Embeddings:** OpenAI `text-embedding-3-small` (1536-dim), batch API.
  The first index used Gemini `gemini-embedding-2` (3072-dim), but the
  Gemini free tier exhausted on Nov 7, 2026 (429s on embeddings and
  generation, stalling the eval at Q01), so the index was re-embedded
  with OpenAI after the user reloaded $5 of API credit. The Gemini
  index is kept in `data/index/gemini-archive/`. Re-embedding 605
  chunks took 17 seconds and cost ~$0.003.
- **Generation + reranking + judging:** OpenAI `gpt-4o-mini`.
  (Gemini `gemini-3-flash-preview` is kept as the fallback in
  `src/gemini_client.py`; `gemini-2.5-flash` / `-lite` return 404 and
  `gemini-flash-latest` returned 503 on this key as of Nov 7, 2026.)
- **Vector store (default):** local NumPy index — no extra service, no
  extra key. **Optional Pinecone backend** (`src/vector_store.py`,
  `PINECONE_API_KEY` + `PINECONE_INDEX`); the app falls back to local
  when no key is set. No Pinecone key is bundled in this repo.
- **Faithfulness:** every factual claim must cite a retrieved passage
  (`[1]`, `[2]` …); unanswerable questions abstain instead of hallucinating.

## How to run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1. Scrape the corpus (already done; results are in data/raw/)
python -m src.scrape

# 2. Chunk + embed + index (uses the stored OpenAI credential via the
#    workspace helper; no key to paste in)
python -m src.ingest --reindex

# 3. Ask a question from the CLI
python -m scripts.ask "How many paid sick days does GitLab give each team member?"

# 4. Or run the web app
streamlit run app.py

# 5. Run the 15-question evaluation
python -m scripts.run_eval
```

OpenAI access uses the same stored-credential helper as the workspace
`openai.py` CLI — the key is never read, printed, or stored in this
repo. If you run this outside Muse, set the credential up the same way
or adapt `src/openai_client.py` to read `OPENAI_API_KEY` from `.env`.

## Evaluation

15 questions (see `src/eval_questions.py`): 6 straightforward, 2 ambiguous,
3 multi-document, 3 unanswerable (must abstain), 1 edge case (long-page
retrieval). Each run records retrieval hit rate, LLM-judged faithfulness
(grounded / partial / ungrounded), fact correctness, and latency.
Full results: `EVAL_REPORT.md` (and raw JSON in `data/eval_results.json`).

Measured (Nov 7, 2026, 15 questions): retrieval hit rate 12/12 (100%),
correct abstention 3/3, grounded 8/15, fact correct 9/15, latency mean
7.0s / p95 5.5s. Total OpenAI cost for the re-embed + full eval: ~$0.011
of the $5.00 credit. Full detail: EVAL_REPORT.md.

## What breaks first

See `EVAL_REPORT.md` — the honest failure analysis. Headline risks:
long handbook pages dilute the signal (talent-assessment is ~85k chars),
ambiguous "time off" questions need the model to disambiguate PTO vs sick
vs parental leave, and multi-document answers tend to cover the core
fact but omit secondary details (see EVAL_REPORT.md). The Gemini
free-tier rate limit (429s) that stalled the first eval is avoided by
running on OpenAI, at ~$0.01 per full eval.

## Limitations

- Knowledge is frozen at scrape time (Nov 7, 2026). The handbook changes;
  re-run `src/scrape.py` + `src.ingest.py` to refresh.
- Only the 29 People Group pages listed in the manifest are covered —
  expenses, compensation bands, and other handbook sections are not in
  this knowledge base, and the bot will (correctly) say so.
- LLM reranking and judging add latency and a second model call per query;
  `--no-rerank` disables reranking for a faster, slightly weaker path.

## Files

| File | What it is |
| --- | --- |
| `src/scrape.py` | Corpus scraper + manifest |
| `src/chunking.py` | Paragraph-aware chunking (1200/200) |
| `src/openai_client.py` | OpenAI generate + embed (stored credential) |
| `src/gemini_client.py` | Gemini generate + embed (fallback, stored credential) |
| `src/vector_store.py` | Local NumPy store + optional Pinecone |
| `src/bm25.py` | Keyword BM25 |
| `src/retrieve.py` | Hybrid RRF + LLM rerank |
| `src/qa.py` | Cited answer generation + abstention |
| `src/ingest.py` | Chunk + embed + index pipeline |
| `src/eval_questions.py` | The 15-question eval set |
| `scripts/ask.py` | CLI question answering |
| `scripts/run_eval.py` | Eval runner + LLM judge |
| `app.py` | Streamlit UI |
| `PROJECT_DOC.md` | Course write-up (Google Doc draft) |
| `DEMO_SCRIPT.md` | Under-5-minute demo script |
| `EVAL_REPORT.md` | Eval results + failure analysis |
