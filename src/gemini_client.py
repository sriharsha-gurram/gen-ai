"""Gemini API client using the stored `custom.gemini` credential.

Uses the same surrogate-credential helper pattern as the workspace CLIs
(~/workspace/custom-connectors/custom.legacy-gemini/bin/gemini_generate.py):
the raw key is never read, printed, logged, or persisted here. Only
surrogate values are sent, and only to generativelanguage.googleapis.com.

Verified Nov 7, 2026 (free tier):
  - generation: gemini-3-flash-preview  (gemini-2.5-flash / -lite return 404,
    gemini-flash-latest returned 503 — do not retry those)
  - embeddings: gemini-embedding-002 is the working model (3072-dim).
    gemini-embedding-001 hit its free-tier quota on Nov 7 after ~570
    chunks (429 even after 5-minute waits) while gemini-embedding-2
    still answered — the quota is per-model, so this client uses -2.
"""
from __future__ import annotations

import importlib.util
import json
import time
import urllib.request

HELPER_PATH = "/opt/muse/skills/custom-connector-setup/bin/dynamic_credentials.py"
CREDENTIAL_NAME = "custom.gemini"
ALLOWED_HOSTS = ["generativelanguage.googleapis.com"]
BASE = "https://generativelanguage.googleapis.com/v1beta/models"

GENERATION_MODEL = "gemini-3-flash-preview"
EMBEDDING_MODEL = "gemini-embedding-2"
EMBEDDING_DIM = 3072


def _load_helper():
    spec = importlib.util.spec_from_file_location("dynamic_credentials", HELPER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _post(helper, url: str, body: dict, timeout: int = 120) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    helper.add_surrogate_to_request(req, CREDENTIAL_NAME, allowed_hosts=ALLOWED_HOSTS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return helper.read_json_response(resp)


def generate(prompt: str, model: str = GENERATION_MODEL) -> str:
    """One generateContent call, with backoff on 429s. Returns plain text
    ('' on empty)."""
    helper = _load_helper()
    result = None
    for attempt in range(4):
        try:
            result = _post(helper, f"{BASE}/{model}:generateContent",
                           {"contents": [{"parts": [{"text": prompt}]}]})
            break
        except Exception as exc:  # noqa: BLE001 - 429s surface as HTTPError
            if "429" in str(exc) and attempt < 3:
                wait = 30 * (2 ** attempt)
                print(f"  generate rate-limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            raise
    if "error" in result:
        raise RuntimeError(f"Gemini generate error: {json.dumps(result['error'])[:300]}")
    parts = []
    for cand in result.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            if "text" in part:
                parts.append(part["text"])
    return "\n".join(parts)


def embed_texts(texts: list[str], model: str = EMBEDDING_MODEL,
                batch_size: int = 10) -> list[list[float]]:
    """Batch-embed via batchEmbedContents. Returns one vector per input text,
    in input order. Free-tier friendly: small batches, a pause between
    batches, and exponential backoff on 429 rate-limit responses."""
    helper = _load_helper()
    vectors: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        body = {"requests": [
            {"model": f"models/{model}",
             "content": {"parts": [{"text": t}]},
             "taskType": "RETRIEVAL_DOCUMENT"} for t in batch]}
        result = None
        for attempt in range(6):
            try:
                result = _post(helper, f"{BASE}/{model}:batchEmbedContents", body)
                break
            except Exception as exc:  # noqa: BLE001 - 429s surface as HTTPError
                if "429" in str(exc) and attempt < 5:
                    wait = min(30 * (2 ** attempt), 300)
                    print(f"  rate-limited, waiting {wait}s "
                          f"(batch {i // batch_size + 1})...")
                    time.sleep(wait)
                    continue
                raise
        if result is None or "error" in result:
            raise RuntimeError(
                f"Gemini embed error: {json.dumps(result.get('error', {}))[:300]}")
        for emb in result.get("embeddings", []):
            vectors.append(emb["values"])
        if i + batch_size < len(texts):
            time.sleep(5)
    if len(vectors) != len(texts):
        raise RuntimeError(f"Embedding count mismatch: {len(vectors)} vs {len(texts)}")
    return vectors


def embed_query(text: str, model: str = EMBEDDING_MODEL) -> list[float]:
    """Single embedContent call, with the same 429 backoff as generate()."""
    helper = _load_helper()
    body = {"model": f"models/{model}",
            "content": {"parts": [{"text": text}]},
            "taskType": "RETRIEVAL_QUERY"}
    result = None
    for attempt in range(5):
        try:
            result = _post(helper, f"{BASE}/{model}:embedContent", body)
            break
        except Exception as exc:  # noqa: BLE001 - 429s surface as HTTPError
            if "429" in str(exc) and attempt < 4:
                wait = min(30 * (2 ** attempt), 300)
                print(f"  embed rate-limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            raise
    if result is None or "error" in result:
        raise RuntimeError(
            f"Gemini embed error: {json.dumps((result or {}).get('error', {}))[:300]}")
    return result["embedding"]["values"]
