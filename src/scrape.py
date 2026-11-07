"""Scrape the public GitLab Handbook (People Group / HR sections) into
data/raw/ as Markdown + a corpus manifest.

Source: https://handbook.gitlab.com — GitLab publishes its handbook openly
under a Creative Commons Attribution-ShareAlike 4.0 licence (CC BY-SA 4.0);
see https://handbook.gitlab.com/handbook/company/culture/all-remote/ and the
handbook footer. No login, no paywall. Polite: one request at a time with a
small delay, identifiable User-Agent, only the ~20 pages listed below.
"""
from __future__ import annotations

import json
import re
import time
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = "https://handbook.gitlab.com"
HEADERS = {"User-Agent": "GenAcademy-Week2-RAG-CourseProject/1.0 (educational research)"}

# Curated People/HR policy pages. Verified live Nov 7, 2026 from the
# People Group index page. Pages that 404 or come back too short are
# dropped by the scraper and noted in the manifest.
CANDIDATE_URLS = [
    ("time-off-and-absence", f"{BASE}/handbook/people-group/time-off-and-absence"),
    ("general-onboarding", f"{BASE}/handbook/people-group/general-onboarding"),
    ("acceptable-use-policy", f"{BASE}/handbook/people-group/acceptable-use-policy"),
    ("anti-harassment", f"{BASE}/handbook/people-group/anti-harassment"),
    ("learning-and-development", f"{BASE}/handbook/people-group/learning-and-development"),
    ("promotions-transfers", f"{BASE}/handbook/people-group/promotions-transfers"),
    ("talent-assessment", f"{BASE}/handbook/people-group/talent-assessment"),
    ("360-feedback", f"{BASE}/handbook/people-group/360-feedback"),
    ("competencies", f"{BASE}/handbook/people-group/competencies"),
    ("relocation", f"{BASE}/handbook/people-group/relocation"),
    ("visas", f"{BASE}/handbook/people-group/visas"),
    ("offboarding", f"{BASE}/handbook/people-group/offboarding"),
    ("celebrations", f"{BASE}/handbook/people-group/celebrations"),
    ("employment-solutions", f"{BASE}/handbook/people-group/employment-solutions"),
    ("team-member-relations", f"{BASE}/handbook/people-group/team-member-relations"),
    ("engagement", f"{BASE}/handbook/people-group/engagement"),
    ("all-remote", f"{BASE}/handbook/company/culture/all-remote"),
    ("guidance-on-feedback", f"{BASE}/handbook/people-group/guidance-on-feedback"),
    ("quarterly-talent-review", f"{BASE}/handbook/people-group/quarterly-talent-review"),
    ("people-compliance", f"{BASE}/handbook/people-group/people-compliance"),
    ("pronouns", f"{BASE}/handbook/people-group/pronouns"),
    ("givelab-volunteer", f"{BASE}/handbook/people-group/givelab-volunteer-initiatives"),
    ("people-group-index", f"{BASE}/handbook/people-group/"),
]

# Extra discovery: follow in-page links from these two hub pages, keep only
# People Group sub-pages (leave, onboarding checklists, etc.).
HUBS = [
    f"{BASE}/handbook/people-group/time-off-and-absence",
    f"{BASE}/handbook/people-group/general-onboarding",
]

MIN_CHARS = 800


def extract_main_text(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup.find("article") or soup
    title = ""
    h1 = main.find("h1")
    if h1:
        title = h1.get_text(strip=True)
    # Drop nav / edit links / code blocks that are not policy prose.
    for tag in main.find_all(["nav", "script", "style", "noscript"]):
        tag.decompose()
    text = main.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return title, text


def fetch(url: str, session: requests.Session) -> str | None:
    try:
        r = session.get(url, headers=HEADERS, timeout=30)
    except requests.RequestException as exc:
        print(f"  FAIL {url}: {exc}")
        return None
    if r.status_code != 200:
        print(f"  HTTP {r.status_code} {url}")
        return None
    return r.text


def discover(session: requests.Session) -> list[tuple[str, str]]:
    extra: list[tuple[str, str]] = []
    seen = {u for _, u in CANDIDATE_URLS}
    for hub in HUBS:
        html = fetch(hub, session)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        main = soup.find("main") or soup
        for a in main.find_all("a", href=True):
            href = a["href"].split("#")[0].rstrip("/")
            if "handbook/people-group/" in href and href.startswith("http"):
                if href not in seen and "internal.gitlab.com" not in href:
                    slug = href.rstrip("/").split("/")[-1]
                    extra.append((slug, href))
                    seen.add(href)
        time.sleep(1)
    return extra


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    raw_dir = root / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    urls = list(CANDIDATE_URLS) + discover(session)
    print(f"Scraping {len(urls)} candidate pages...")
    manifest_docs = []
    dropped = []
    for slug, url in urls:
        html = fetch(url, session)
        time.sleep(1)
        if not html:
            dropped.append({"slug": slug, "url": url, "reason": "fetch failed"})
            continue
        title, text = extract_main_text(html)
        if len(text) < MIN_CHARS:
            dropped.append({"slug": slug, "url": url,
                            "reason": f"too short ({len(text)} chars)"})
            print(f"  SHORT {url} ({len(text)} chars)")
            continue
        out = raw_dir / f"{slug}.md"
        out.write_text(f"# {title or slug}\n\nSource: {url}\n\n{text}\n",
                       encoding="utf-8")
        manifest_docs.append({
            "slug": slug, "title": title or slug, "url": url,
            "chars": len(text), "words": len(text.split()),
            "file": f"data/raw/{slug}.md",
        })
        print(f"  OK {slug}: {len(text)} chars")
    manifest = {
        "corpus": "GitLab Handbook — People Group / HR policy sections",
        "source_site": "https://handbook.gitlab.com",
        "license": "CC BY-SA 4.0 (GitLab Handbook, as stated in the handbook footer)",
        "scraped_on": str(date.today()),
        "scraper": "src/scrape.py (requests + BeautifulSoup, 1s delay, no login)",
        "doc_count": len(manifest_docs),
        "total_chars": sum(d["chars"] for d in manifest_docs),
        "total_words": sum(d["words"] for d in manifest_docs),
        "documents": manifest_docs,
        "dropped": dropped,
    }
    (root / "data" / "corpus_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nDone: {len(manifest_docs)} docs, "
          f"{manifest['total_words']} words, {len(dropped)} dropped.")


if __name__ == "__main__":
    main()
