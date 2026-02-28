#!/usr/bin/env python3
"""Build a daily flash-card digest from an OPML feed list."""

from __future__ import annotations

import argparse
import email.utils
import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

CATEGORY_ORDER = ("GenAI", "Azure", "GCP", "AWS", "Industry")


@dataclass(frozen=True)
class FeedSource:
    name: str
    category: str
    rss_url: str
    html_url: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate daily digest JSON from OPML feeds.")
    parser.add_argument("--opml", required=True, help="Path to OPML file exported from Feeder.")
    parser.add_argument("--output", required=True, help="Output JSON file path.")
    parser.add_argument("--max-stories", type=int, default=40, help="Max stories in final digest.")
    parser.add_argument("--days", type=int, default=2, help="Include stories newer than N days.")
    parser.add_argument("--timeout", type=int, default=12, help="HTTP timeout in seconds per feed.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    opml_path = Path(args.opml)
    output_path = Path(args.output)
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)

    feeds = extract_feeds_from_opml(opml_path)
    stories = []
    for feed in feeds:
        for item in fetch_feed_items(feed, timeout=args.timeout):
            published = parse_date(item.get("publishedAt"))
            if published and published < cutoff:
                continue
            story = {
                "category": feed.category,
                "source": feed.name,
                "title": item["title"],
                "summary": summarize(item["description"]),
                "details": build_details(item["description"], feed.category),
                "url": item["url"] or feed.html_url or feed.rss_url,
                "publishedAt": (published or datetime.now(timezone.utc)).isoformat().replace("+00:00", "Z"),
            }
            stories.append(story)

    stories = dedupe_and_sort(stories)[: args.max_stories]

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "sourceFile": str(opml_path.name),
        "feeds": [feed.__dict__ for feed in feeds],
        "stories": stories,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {len(stories)} stories from {len(feeds)} feeds to {output_path}")
    return 0


def extract_feeds_from_opml(opml_path: Path) -> list[FeedSource]:
    tree = ET.parse(opml_path)
    root = tree.getroot()
    feeds: list[FeedSource] = []
    seen_urls: set[str] = set()
    for node in root.findall(".//outline"):
        rss_url = (node.attrib.get("xmlUrl") or "").strip()
        if not rss_url or rss_url in seen_urls:
            continue
        seen_urls.add(rss_url)
        name = (node.attrib.get("title") or node.attrib.get("text") or "Unknown Feed").strip()
        html_url = (node.attrib.get("htmlUrl") or "").strip()
        feeds.append(
            FeedSource(
                name=name,
                category=infer_category(name=name, rss_url=rss_url),
                rss_url=rss_url,
                html_url=html_url,
            )
        )
    return feeds


def infer_category(name: str, rss_url: str) -> str:
    text = f"{name} {rss_url}".lower()
    keyword_map = {
        "Azure": ("azure", "microsoft"),
        "GCP": ("google cloud", "gcp", "withgoogle", "cloud.google"),
        "AWS": ("aws", "amazonwebservices", "amazon web services", "feedburner"),
        "GenAI": ("ai", "llm", "genai", "model", "openai", "foundry", "mcp"),
    }
    for category in ("Azure", "GCP", "AWS", "GenAI"):
        if any(token in text for token in keyword_map[category]):
            return category
    return "Industry"


def fetch_feed_items(feed: FeedSource, timeout: int) -> Iterable[dict]:
    try:
        request = urllib.request.Request(
            feed.rss_url,
            headers={"User-Agent": "DailyBriefBot/1.0 (+https://github.com/)"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except (urllib.error.URLError, TimeoutError, ValueError):
        return []

    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []

    tag = strip_ns(root.tag)
    if tag == "rss":
        return parse_rss(root)
    if tag == "feed":
        return parse_atom(root)
    return []


def parse_rss(root: ET.Element) -> list[dict]:
    items = []
    for item in root.findall("./channel/item"):
        title = clean_text(get_child_text(item, "title"))
        if not title:
            continue
        link = clean_text(get_child_text(item, "link"))
        description = clean_text(get_child_text(item, "description")) or clean_text(get_child_text(item, "content:encoded"))
        published_at = clean_text(get_child_text(item, "pubDate")) or clean_text(get_child_text(item, "dc:date"))
        items.append(
            {
                "title": title,
                "url": link,
                "description": description,
                "publishedAt": normalize_date(published_at),
            }
        )
    return items


def parse_atom(root: ET.Element) -> list[dict]:
    items = []
    ns = {"a": root.tag.split("}")[0].strip("{")} if "}" in root.tag else {}
    entries = root.findall("./a:entry", ns) if ns else root.findall("./entry")
    for entry in entries:
        title = clean_text(get_child_text(entry, "title"))
        if not title:
            continue
        link = atom_link(entry, ns)
        description = clean_text(get_child_text(entry, "summary")) or clean_text(get_child_text(entry, "content"))
        published_at = clean_text(get_child_text(entry, "updated")) or clean_text(get_child_text(entry, "published"))
        items.append(
            {
                "title": title,
                "url": link,
                "description": description,
                "publishedAt": normalize_date(published_at),
            }
        )
    return items


def atom_link(entry: ET.Element, ns: dict) -> str:
    links = entry.findall("a:link", ns) if ns else entry.findall("link")
    for link in links:
        if link.attrib.get("rel", "alternate") == "alternate":
            return link.attrib.get("href", "").strip()
    if links:
        return links[0].attrib.get("href", "").strip()
    return ""


def get_child_text(node: ET.Element, child_tag: str) -> str:
    if ":" in child_tag:
        _, local = child_tag.split(":", 1)
        child = node.find(f".//{{*}}{local}")
    else:
        child = node.find(child_tag)
        if child is None:
            child = node.find(f".//{{*}}{child_tag}")
    return child.text if child is not None and child.text else ""


def clean_text(value: str) -> str:
    if not value:
        return ""
    no_tags = re.sub(r"<[^>]+>", " ", value)
    no_entities = (
        no_tags.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )
    return re.sub(r"\s+", " ", no_entities).strip()


def summarize(text: str, max_words: int = 24) -> str:
    base = text or "New update published. Open the source link for full details."
    words = base.split()
    if len(words) <= max_words:
        return base
    return " ".join(words[:max_words]).rstrip(".,;:") + "..."


def build_details(text: str, category: str) -> str:
    guidance = {
        "GenAI": "Watch for model capability, latency, and governance impact.",
        "Azure": "Check service rollout region, GA vs preview status, and migration effort.",
        "GCP": "Focus on Vertex, data platform integration, and operational constraints.",
        "AWS": "Review launch regions, pricing model, and workload fit before adoption.",
        "Industry": "Track market signal, enterprise adoption trend, and competitive response.",
    }
    detail = summarize(text, max_words=45)
    return f"{detail} {guidance.get(category, guidance['Industry'])}".strip()


def normalize_date(raw: str) -> str:
    if not raw:
        return ""
    parsed = parse_date(raw)
    return parsed.isoformat().replace("+00:00", "Z") if parsed else ""


def parse_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip()
    for parser in (parse_iso, parse_rfc2822):
        parsed = parser(raw)
        if parsed:
            return parsed
    return None


def parse_iso(raw: str) -> datetime | None:
    normalized = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def parse_rfc2822(raw: str) -> datetime | None:
    try:
        dt = email.utils.parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def dedupe_and_sort(stories: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    unique: list[dict] = []
    for story in stories:
        key = (story["title"], story["url"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(story)
    unique.sort(key=lambda item: item.get("publishedAt", ""), reverse=True)
    return unique


def strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


if __name__ == "__main__":
    sys.exit(main())
