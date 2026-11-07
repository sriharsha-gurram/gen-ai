"""Streamlit UI for the Enterprise Policy Q&A Bot.

Run:  streamlit run app.py
Ask a question about GitLab HR policies, get a cited answer plus the
retrieved passages. The sidebar shows the corpus, the stack, and the
retrieval settings used for the current answer.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.qa import build_answer  # noqa: E402
from src.retrieve import Retriever  # noqa: E402
from src.vector_store import get_store  # noqa: E402

SAMPLE_QUESTIONS = [
    "How many paid sick days does GitLab give each team member?",
    "How long is GitLab's paid parental leave, and who is eligible?",
    "What is an onboarding buddy, and who can volunteer as one?",
    "Does GitLab have a fixed number of paid time off days per year?",
    "What happens to my GitLab access and equipment when I leave?",
    "What is the Wi-Fi password for the GitLab office in San Francisco?",
]

st.set_page_config(page_title="GitLab Policy Q&A (RAG)", page_icon="📋")
st.title("📋 GitLab Policy Q&A Bot")
st.write("Ask a question about GitLab HR policies. Answers come only from "
         "the GitLab Handbook pages in the knowledge base, with citations. "
         "If the answer is not in the handbook, the bot says so instead of "
         "guessing.")

manifest = json.loads((ROOT / "data" / "corpus_manifest.json").read_text())
st.sidebar.header("Knowledge base")
st.sidebar.write(f"**{manifest['doc_count']} handbook pages**, "
                 f"{manifest['total_words']:,} words")
st.sidebar.write("Source: GitLab Handbook (CC BY-SA 4.0)")
st.sidebar.write("Corpus: People Group / HR policy sections, "
                 f"scraped {manifest['scraped_on']}")
st.sidebar.header("Stack")
st.sidebar.write("- Embeddings: OpenAI `text-embedding-3-small` (1536-dim)")
st.sidebar.write("- Generation: OpenAI `gpt-4o-mini`")
st.sidebar.write("- Retrieval: hybrid BM25 + semantic, RRF fusion, LLM rerank")
st.sidebar.write("- Vector store: local NumPy index "
                 "(Pinecone optional via `PINECONE_API_KEY`)")

with st.sidebar.expander("Pages in the knowledge base"):
    for d in manifest["documents"]:
        st.sidebar.write(f"- {d['title']}")


@st.cache_resource
def load_retriever():
    store, backend = get_store(ROOT / "data" / "index")
    if backend == "local-numpy" and not store.load():
        return None, backend, "No local index found. Run: python -m src.ingest"
    if backend == "pinecone":
        store.chunks = json.loads(
            (ROOT / "data" / "index" / "chunks.json").read_text())
    return Retriever(store, store.chunks), backend, None


retriever, backend, error = load_retriever()
if error:
    st.error(error)
    st.stop()
st.sidebar.write(f"Vector store: **{backend}**")

question = st.text_input("Your question", placeholder="e.g. How many paid sick days do I get?")
cols = st.columns(3)
for i, sample in enumerate(SAMPLE_QUESTIONS):
    if cols[i % 3].button(sample, key=f"sample-{i}"):
        question = sample

rerank = st.checkbox("LLM reranking (slower, more accurate)", value=True)

if question:
    with st.spinner("Searching the handbook..."):
        t0 = time.time()
        retrieved = retriever.retrieve(question, top_k=4, rerank=rerank)
        result = build_answer(question, retrieved)
        elapsed = time.time() - t0
    st.subheader("Answer")
    st.write(result["answer"])
    st.caption(f"Answered in {elapsed:.1f}s using {backend} retrieval. "
               f"Abstained: {result['abstained']}")
    st.subheader("Sources")
    for s in result["sources"]:
        st.write(f"[{s['n']}] **{s['doc_title']}** — [{s['source_url']}]({s['source_url']})")
    with st.expander("Retrieved passages (what the answer was built from)"):
        for i, c in enumerate(retrieved):
            st.write(f"**[{i + 1}] {c['doc_title']}**")
            st.write(c["text"][:1200])
