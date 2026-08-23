#!/usr/bin/env python3
"""Fetch and parse one official YouTube channel RSS feed request."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse


FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)
CHANNEL_ID_RE = re.compile(r"^UC[A-Za-z0-9_-]{22}$")
NAMESPACES = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
}


def parse_channel_id(value: str) -> str:
    """Return a YouTube channel ID from a raw ID or official /channel/ URL."""
    candidate = value.strip()
    if CHANNEL_ID_RE.fullmatch(candidate):
        return candidate

    parsed = urlparse(candidate)
    host = (parsed.hostname or "").lower()
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[0] == "channel" and CHANNEL_ID_RE.fullmatch(parts[1]):
            return parts[1]

    raise ValueError(
        "Expected a UC... channel ID or an official YouTube /channel/UC... URL. "
        "Resolve @handle URLs to the official channel ID first."
    )


def child_text(element: ET.Element, path: str) -> Optional[str]:
    child = element.find(path, NAMESPACES)
    if child is None or child.text is None:
        return None
    value = child.text.strip()
    return value or None


def parse_feed(xml_text: str, requested_channel_id: str) -> dict[str, Any]:
    """Parse a YouTube Atom feed into compact JSON-ready records."""
    root = ET.fromstring(xml_text)
    feed_channel_id = child_text(root, "yt:channelId")
    channel_id = (
        feed_channel_id
        if feed_channel_id and CHANNEL_ID_RE.fullmatch(feed_channel_id)
        else requested_channel_id
    )
    channel_title = child_text(root, "atom:title")
    entries: list[dict[str, Optional[str]]] = []

    for entry in root.findall("atom:entry", NAMESPACES):
        video_id = child_text(entry, "yt:videoId")
        if not video_id:
            continue
        entries.append(
            {
                "video_id": video_id,
                "title": child_text(entry, "atom:title"),
                "channel": child_text(entry, "atom:author/atom:name") or channel_title,
                "channel_id": child_text(entry, "yt:channelId") or channel_id,
                "published": child_text(entry, "atom:published"),
                "updated": child_text(entry, "atom:updated"),
                "url": f"https://www.youtube.com/watch?v={video_id}",
            }
        )

    return {
        "channel_id": channel_id,
        "channel": channel_title,
        "feed_url": FEED_URL.format(channel_id=requested_channel_id),
        "entry_count": len(entries),
        "entries": entries,
    }


def fetch_channel_feed(channel_id: str, timeout: float = 20.0) -> dict[str, Any]:
    """Issue exactly one feed request and return parsed records."""
    feed_url = FEED_URL.format(channel_id=channel_id)
    request = urllib.request.Request(
        feed_url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/atom+xml, application/xml;q=0.9, */*;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        xml_text = response.read().decode("utf-8")

    result = parse_feed(xml_text, channel_id)
    result["fetched_at"] = datetime.now(timezone.utc).isoformat()
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch recent uploads from one official YouTube channel RSS feed request."
    )
    parser.add_argument("channel", help="UC... channel ID or official /channel/UC... URL")
    parser.add_argument("--output", help="Write JSON to this path instead of stdout")
    parser.add_argument("--timeout", type=float, default=20.0, help="Request timeout in seconds")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        channel_id = parse_channel_id(args.channel)
        result = fetch_channel_feed(channel_id, timeout=args.timeout)
    except (ValueError, ET.ParseError, UnicodeDecodeError, urllib.error.URLError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
