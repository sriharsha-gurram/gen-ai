"""Briefing rendering.

The comparison table and the per-competitor fact blocks are rendered
deterministically from the extracted fields, so the table cannot invent
a value the extractor did not find. The LLM writes only the prose
(what-to-watch note and the per-competitor narrative), and every claim
it writes must carry a [n] citation to a source URL from the run.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

NOT_FOUND = "not found in sources"

# Phrases that mark a sentence as an absence statement — a statement
# about what the run did NOT find. No source states an absence, so a
# citation after such a sentence is misleading even when the number
# points at a real page (the page does not say the thing is missing).
_ABSENCE_PATTERNS = [
    r"there\s+are\s+no\b",
    r"there\s+is\s+no\b",
    r"there\s+were\s+no\b",
    r"\bno\s+information\b",
    r"\bno\s+details\s+available\b",
    r"\bno\s+available\s+(information|sources?)\b",
    r"\bno\s+recent\s+news\b",
    r"\bnot\s+found\s+in\s+(the\s+)?sources\b",
    r"\bwas\s+not\s+found\b",
    r"\bwere\s+not\s+found\b",
    r"\bno\s+news\s+(items\s+)?available\b",
]
_ABSENCE_RE = re.compile("|".join(_ABSENCE_PATTERNS), re.I)
_CITATION_RE = re.compile(r"\[\d+\]")


def _enforce_inference_labels(text: str) -> str:
    """Every bullet in '## What to watch' is forward-looking by
    definition — a judgement about what could change the comparison.
    A bullet without the '(analyst inference)' label gets it, and any
    citation it carries is dropped: a citation must not make a
    prediction look like a sourced fact. Bullets already labelled are
    untouched."""
    lines = text.splitlines()
    out: list[str] = []
    in_watch = False
    for line in lines:
        if line.startswith("## "):
            in_watch = line.strip().lower() == "## what to watch"
            out.append(line)
            continue
        if (in_watch and line.strip().startswith("- ")
                and "(analyst inference)" not in line):
            s = _CITATION_RE.sub("", line.rstrip())
            s = re.sub(r"\s+([.!?])", r"\1", s)
            if s.endswith("."):
                s = s[:-1].rstrip() + " (analyst inference)."
            else:
                s = s + " (analyst inference)"
            out.append(s)
            continue
        out.append(line)
    return "\n".join(out)


def strip_absence_citations(text: str) -> str:
    """Remove [n] citations from absence statements ('there are no…',
    'not found in sources', …). The model paraphrases absences in many
    ways, so the check is pattern-based, not tied to the canonical
    'not found in sources' phrasing. Factual sentences are untouched.
    """
    def _fix_sentence(sent: str) -> str:
        if _ABSENCE_RE.search(sent):
            stripped = _CITATION_RE.sub("", sent)
            if stripped != sent:
                # Removing "[15]" leaves "word ." — close the gap.
                stripped = re.sub(r"\s+([.!?])", r"\1", stripped)
            return stripped
        return sent

    out_lines = []
    for line in text.splitlines():
        parts = re.split(r"(?<=[.!?])\s+", line)
        fixed = [_fix_sentence(p) for p in parts]
        # Leave untouched lines byte-identical: rejoining would
        # normalise double spaces and trailing whitespace.
        out_lines.append(" ".join(fixed) if fixed != parts else line)
    return "\n".join(out_lines)


def _field(value) -> str:
    if isinstance(value, dict):
        value = value.get("value", "")
    value = (value or "").strip()
    return value if value else NOT_FOUND


def render_comparison_table(extracted: dict[str, dict]) -> str:
    names = list(extracted.keys())
    rows = [
        "| | " + " | ".join(names) + " |",
        "|---|---|" + "---|" * (len(names) - 1),
    ]
    for label, key in [
        ("Pricing model", "pricing_model"),
        ("Starting price", "starting_price"),
        ("Positioning", "positioning"),
    ]:
        rows.append("| " + label + " | " +
                    " | ".join(_field(extracted[n].get(key)) for n in names) + " |")
    return "\n".join(rows)


def render_briefing(state: dict, prose: str) -> str:
    """Assemble the final briefing markdown. ``prose`` is the LLM-written
    narrative (per-competitor pages + what-to-watch), already cited.
    Citations are stripped from absence statements first: no source
    states that something is missing, so a cited absence is a false
    citation even when the number points at a real page. What-to-watch
    bullets are then labelled as analyst inference where the label is
    missing (see _enforce_inference_labels)."""
    prose = _enforce_inference_labels(strip_absence_citations(prose.strip()))
    market = state["market"]
    extracted = state.get("extracted", {})
    sources = []
    for url in state.get("sources", []):
        if url and url not in sources:
            sources.append(url)
    lines = [
        f"# Competitor Briefing — {market}",
        "",
        f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d')} by the "
        f"Week 3 Market Research Agent. Every pricing and feature claim is "
        f"cited to a source URL found during the run; a field the sources "
        f"did not answer is marked \"{NOT_FOUND}\" rather than guessed.",
        "",
        "## Comparison",
        "",
        render_comparison_table(extracted),
        "",
        prose.strip(),
        "",
        "## Sources",
        "",
    ]
    for i, url in enumerate(sources, 1):
        lines.append(f"[{i}] {url}")
    lines.append("")
    lines.append("## Run notes")
    lines.append("")
    lines.append(f"- Tavily credits used: {state.get('credits_used', 0)}")
    lines.append(f"- Providers used: "
                 f"{', '.join(state.get('providers_used', [])) or 'none recorded'}")
    lines.append(f"- Errors and retries: {len(state.get('errors', []))} "
                 f"recorded (see the run file)")
    not_found = [f"{n}: {', '.join(v.get('not_found', []))}"
                 for n, v in extracted.items() if v.get("not_found")]
    if not_found:
        lines.append("- Fields not found in sources:")
        lines.extend(f"  - {item}" for item in not_found)
    return "\n".join(lines)


def render_briefing_json(state: dict) -> dict:
    return {
        "market": state["market"],
        "run_id": state["run_id"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "competitors": state.get("extracted", {}),
        "sources": state.get("sources", []),
        "credits_used": state.get("credits_used", 0),
        "providers_used": state.get("providers_used", []),
        "errors": state.get("errors", []),
        "human_decision": state.get("human_decision"),
    }


def briefing_json_text(state: dict) -> str:
    return json.dumps(render_briefing_json(state), indent=2)
