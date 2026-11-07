"""Tavily search + extract with the stored `custom.tavily` credential.

Same surrogate-credential pattern as the Week 2 clients: the raw key is
never read, printed, logged, or persisted here. Only surrogate values
are sent, and only to api.tavily.com.

Costs on the free Researcher plan (1,000 credits/month, no card):
  - search, basic depth: 1 credit per call (advanced: 2)
  - extract: 1 credit per 5 URLs

The module keeps a running credit counter so the graph can enforce its
quota guard (stop and ask the human above 60 credits per run). Call
``reset_credits()`` at the start of a run; ``credits_used()`` reads it.
"""
from __future__ import annotations

import importlib.util
import json
import math
import time
import urllib.request

HELPER_PATH = "/opt/muse/skills/custom-connector-setup/bin/dynamic_credentials.py"
CREDENTIAL_NAME = "custom.tavily"
ALLOWED_HOSTS = ["api.tavily.com"]
BASE = "https://api.tavily.com"

_CREDITS = 0


class TavilyError(RuntimeError):
    """Raised when Tavily fails after all retries."""


def credits_used() -> int:
    return _CREDITS


def reset_credits() -> None:
    global _CREDITS
    _CREDITS = 0


def _load_helper():
    spec = importlib.util.spec_from_file_location("dynamic_credentials", HELPER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _post(helper, path: str, body: dict, timeout: int = 60) -> dict:
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 method="POST")
    req.add_header("Content-Type", "application/json")
    helper.add_surrogate_to_request(req, CREDENTIAL_NAME, allowed_hosts=ALLOWED_HOSTS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return helper.read_json_response(resp)


def _call_with_retry(path: str, body: dict, cost: int, what: str) -> dict:
    """POST with exponential backoff on 429/5xx. Retries 3 times, then
    raises TavilyError. Credits are charged only on a successful call
    (a failed call is not billed by Tavily)."""
    global _CREDITS
    helper = _load_helper()
    last_exc: Exception | None = None
    for attempt in range(4):
        try:
            result = _post(helper, path, body)
            if "error" in result:
                raise RuntimeError(str(result["error"])[:300])
            _CREDITS += cost
            return result
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            transient = any(s in str(exc) for s in ("429", "500", "502", "503", "504"))
            if transient and attempt < 3:
                wait = 10 * (2 ** attempt)
                print(f"  Tavily {what} hit a transient error, retrying in {wait}s...")
                time.sleep(wait)
                continue
            raise TavilyError(f"Tavily {what} failed: {exc}") from exc
    raise TavilyError(f"Tavily {what} failed: {last_exc}")


def search(query: str, max_results: int = 5, depth: str = "basic",
           time_range: str | None = None) -> list[dict]:
    """Basic search (1 credit). Returns [{url, title, content, score}].
    time_range: day/week/month/year — used for the news search."""
    cost = 1 if depth == "basic" else 2
    body: dict = {
        "query": query, "search_depth": depth,
        "max_results": max_results, "include_answer": False,
    }
    if time_range:
        body["time_range"] = time_range
    result = _call_with_retry("/search", body, cost, "search")
    out = []
    for r in result.get("results", []):
        out.append({
            "url": r.get("url", ""),
            "title": r.get("title", ""),
            "content": (r.get("content") or "")[:2000],
            "score": r.get("score"),
        })
    return out


def extract(urls: list[str]) -> list[dict]:
    """Extract page text. 1 credit per 5 URLs. Returns
    [{url, raw_content}] for pages that returned text; failed URLs are
    omitted here and must be recorded by the caller from the difference."""
    if not urls:
        return []
    cost = max(1, math.ceil(len(urls) / 5))
    result = _call_with_retry("/extract", {"urls": urls}, cost, "extract")
    out = []
    for r in result.get("results", []):
        text = r.get("raw_content") or ""
        if text.strip():
            out.append({"url": r.get("url", ""), "raw_content": text[:12000]})
    return out
