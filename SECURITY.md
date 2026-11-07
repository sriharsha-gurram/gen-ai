# Security policy

This is a public repository. Treat everything in it as visible to anyone.

## What is safe here

- Code, documentation, evaluation results, and the public GitLab Handbook
  corpus under `data/raw/` (CC BY-SA 4.0, source URLs in
  `data/corpus_manifest.json`).
- No API keys, passwords, tokens, or private credentials are committed in
  this repository. A scan for key patterns returns nothing.

## How credentials work

- OpenAI: the code calls the API through a stored credential (in Muse, the
  `custom.openai` connection). The raw key is never read, printed, logged,
  or written to a file by this code. If you run this outside Muse, set
  `OPENAI_API_KEY` in a local `.env` file.
- Gemini: same pattern, stored credential `custom.gemini`. The code in
  `src/gemini_client.py` is kept as a fallback only.
- Pinecone (optional): set `PINECONE_API_KEY` and `PINECONE_INDEX` in
  `.env`. The app works without them, using the local vector store.
- `.env` is gitignored. `.env.example` contains placeholders only, never
  a real value. Never paste a real key into a file, a chat message, a
  commit message, or an issue in this repo.

## If a key leaks

1. Revoke or rotate the key immediately at the provider (OpenAI, Google
   AI Studio, Pinecone). Rotating the key matters more than deleting the
   commit, because git history keeps the old value.
2. Remove the value from the file and commit the fix.
3. If the leak was in an old commit, rewrite that history or contact
   GitHub support about cached views. Assume anything pushed to a public
   repo has been copied.

## What not to add

- Do not add employer internal documents, customer data, or any file with
  personal data (names, emails, phone numbers, addresses, government IDs).
  The corpus here is public handbook content only.
- Do not add `.env`, `data/index/`, `data/eval_results.json`, `.venv/`,
  or any other gitignored output. They are generated locally and are
  excluded by `.gitignore` for this reason.
- Do not paste tracked cohort codes or private links into issues or
  pull requests.

## Reporting a security issue

Open an issue in this repository with the word SECURITY in the title, and
do not include the secret itself in the report.
