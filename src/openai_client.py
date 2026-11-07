"""OpenAI API client using the stored `custom.openai` credential.

Same call shape as src/gemini_client.py (generate / embed_texts /
embed_query) so the pipeline can switch providers by changing one import.

Uses the same surrogate-credential helper pattern as the workspace
connector (~/workspace/custom-connectors/custom.openai/bin/openai.py):
the raw key is never read, printed, logged, or persisted here. Only
surrogate values are sent, and only to api.openai.com.

Why OpenAI, Nov 7, 2026: the Gemini free tier is exhausted — generation
and embeddings both 429 even after multi-minute backoffs, and the eval
stalled with Q02-Q10 all errors. The user reloaded $5 of OpenAI API
credit. text-embedding-3-small (1536-dim) + gpt-4o-mini finish the whole
eval for a few cents: ~971 chunks of embeddings is about $0.004 and
15 questions x 3 model calls (rerank + answer + judge) is about $0.05.

Usage tracking: every call adds to the module-level USAGE counters
(prompt/completion tokens per model). Call usage_summary() to print the
totals and the estimated cost.
"""
from __future__ import annotations

import importlib.util
import json
import time
import urllib.request

HELPER_PATH = "/opt/muse/skills/custom-connector-setup/bin/dynamic_credentials.py"
CREDENTIAL_NAME = "custom.openai"
ALLOWED_HOSTS = ["api.openai.com"]
BASE = "https://api.openai.com/v1"

GENERATION_MODEL = "gpt-4o-mini"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536

# OpenAI list prices, Nov 2026: gpt-4o-mini $0.15 / $0.60 per 1M
# input / output tokens; text-embedding-3-small $0.02 per 1M tokens.
PRICE = {
    GENERATION_MODEL: (0.15 / 1_000_000, 0.60 / 1_000_000),
    EMBEDDING_MODEL: (0.02 / 1_000_000, 0.0),
}

USAGE: dict[str, dict[str, int]] = {}


def _record(model: str, usage: dict | None) -> None:
    if not usage:
        return
    slot = USAGE.setdefault(model, {"prompt_tokens": 0, "completion_tokens": 0})
    slot["prompt_tokens"] += int(usage.get("prompt_tokens", 0))
    slot["completion_tokens"] += int(usage.get("completion_tokens", 0))


def usage_summary() -> str:
    """Human-readable usage + cost estimate, e.g. 'gpt-4o-mini: ... $0.04'."""
    lines = []
    total = 0.0
    for model, u in USAGE.items():
        pin, pout = PRICE.get(model, (0.0, 0.0))
        cost = u["prompt_tokens"] * pin + u["completion_tokens"] * pout
        total += cost
        lines.append(f"{model}: {u['prompt_tokens']} in / "
                     f"{u['completion_tokens']} out tokens, ~${cost:.4f}")
    lines.append(f"Total estimated cost: ~${total:.4f} (of $5.00 credit)")
    return "\n".join(lines)


def _load_helper():
    spec = importlib.util.spec_from_file_location("dynamic_credentials", HELPER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _post(helper, path: str, body: dict, timeout: int = 120) -> dict:
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 method="POST")
    req.add_header("Content-Type", "application/json")
    helper.add_surrogate_to_request(req, CREDENTIAL_NAME, allowed_hosts=ALLOWED_HOSTS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return helper.read_json_response(resp)


def generate(prompt: str, model: str = GENERATION_MODEL) -> str:
    """One chat completion. Retries once on a transient 429/5xx."""
    helper = _load_helper()
    result = None
    for attempt in range(2):
        try:
            result = _post(helper, "/chat/completions", {
                "model": model,
                "messages": [{"role": "user", "content": prompt}]})
            break
        except Exception as exc:  # noqa: BLE001
            if attempt == 0 and ("429" in str(exc) or "500" in str(exc)
                                 or "503" in str(exc)):
                print("  OpenAI generate hit a transient error, retrying in 10s...")
                time.sleep(10)
                continue
            raise
    _record(model, result.get("usage"))
    if "error" in result:
        raise RuntimeError(f"OpenAI generate error: {json.dumps(result['error'])[:300]}")
    return result["choices"][0]["message"]["content"]


def embed_texts(texts: list[str], model: str = EMBEDDING_MODEL,
                batch_size: int = 100) -> list[list[float]]:
    """Batch-embed via /v1/embeddings (accepts a list of inputs).
    Returns one vector per input text, in input order."""
    helper = _load_helper()
    vectors: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        result = _post(helper, "/embeddings",
                       {"model": model, "input": batch})
        if "error" in result:
            raise RuntimeError(
                f"OpenAI embed error: {json.dumps(result['error'])[:300]}")
        _record(model, result.get("usage"))
        vectors.extend(d["embedding"] for d in result["data"])
    if len(vectors) != len(texts):
        raise RuntimeError(f"Embedding count mismatch: {len(vectors)} vs {len(texts)}")
    return vectors


def embed_query(text: str, model: str = EMBEDDING_MODEL) -> list[float]:
    """Single-query embedding (same model as the index — never mix)."""
    return embed_texts([text], model=model)[0]
