"""LLM router for the Week 3 agent.

Primary: OpenAI gpt-4o-mini via the stored `custom.openai` credential
(proven in Week 2: the full 15-question eval cost ~$0.011). Fallback:
Gemini `gemini-3-flash-preview` via the stored `custom.gemini`
credential, used only if OpenAI fails after its own retries. The
provider actually used is returned so the run log can say so honestly.

No raw keys anywhere: both clients use the surrogate-credential helper
and only talk to their registered hosts.
"""
from __future__ import annotations

import json

from src import gemini_client, openai_client

PROVIDERS_USED: list[str] = []


def generate(prompt: str, json_mode: bool = False) -> tuple[str, str]:
    """Return (text, provider). Raises only if both providers fail."""
    try:
        text = openai_client.generate(prompt, json_mode=json_mode)
        if "openai" not in PROVIDERS_USED:
            PROVIDERS_USED.append("openai")
        return text, "openai"
    except Exception as exc:  # noqa: BLE001
        print(f"  OpenAI generate failed ({exc}); falling back to Gemini...")
    prompt_for_gemini = prompt
    if json_mode:
        prompt_for_gemini = (prompt + "\n\nReply with a single JSON object "
                             "only, no markdown fences, no other text.")
    text = gemini_client.generate(prompt_for_gemini)
    if "gemini" not in PROVIDERS_USED:
        PROVIDERS_USED.append("gemini")
    return text, "gemini"


def generate_json(prompt: str) -> dict:
    """Generate and parse a JSON object. Strips markdown fences first.
    Retries once with a repair prompt if parsing fails."""
    text, provider = generate(prompt, json_mode=True)
    try:
        return _parse_json(text)
    except ValueError:
        repair = (f"The previous reply was not valid JSON. Reply with a "
                  f"single JSON object only, no markdown fences, no other "
                  f"text.\n\nPrevious reply:\n{text[:2000]}")
        text2, provider2 = generate(repair, json_mode=True)
        return _parse_json(text2)


def _parse_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    obj = json.loads(cleaned)
    if not isinstance(obj, dict):
        raise ValueError("LLM did not return a JSON object")
    return obj


def usage_summary() -> str:
    """OpenAI usage + cost (Gemini free tier has no metered cost here)."""
    return openai_client.usage_summary()


def usage_totals() -> dict:
    """Per-model token totals + estimated cost, for the run file."""
    return openai_client.usage_totals()


def reset_usage() -> None:
    """Clear the usage counters at the start of a run."""
    openai_client.reset_usage()
