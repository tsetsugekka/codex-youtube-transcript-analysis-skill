#!/usr/bin/env python3
"""从 YouTube URL 获取字幕并生成可持久保存的 Markdown 文档。"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from datetime import date
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import parse_qs, urljoin, urlparse


VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
ENGLISH_FALLBACK_LANGUAGE = "en"
YOUTUBE_BASE_URL = "https://www.youtube.com"
REQUEST_TIMEOUT_SECONDS = 15
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class YouTubeMetaParser(HTMLParser):
    """从 YouTube 页面中的 meta 标签提取基础字段。"""

    def __init__(self) -> None:
        super().__init__()
        self.values: dict[str, str] = {}

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, Optional[str]]]
    ) -> None:
        if tag != "meta":
            return
        attributes = {key: value for key, value in attrs if value is not None}
        key = attributes.get("itemprop") or attributes.get("property") or attributes.get("name")
        content = attributes.get("content")
        if key and content and key not in self.values:
            self.values[key] = unescape(content)


def extract_video_id(value: str) -> str:
    """从常见 YouTube URL 或 11 位 video ID 中提取 video ID。"""
    value = value.strip()
    if VIDEO_ID_RE.fullmatch(value):
        return value

    candidate = value if "://" in value else f"https://{value}"
    parsed = urlparse(candidate)
    host = parsed.netloc.lower().split(":", 1)[0]
    host = host.removeprefix("www.").removeprefix("m.")

    video_id = ""
    if host in {"youtu.be", "youtube.com", "youtube-nocookie.com"}:
        if host == "youtu.be":
            video_id = parsed.path.lstrip("/").split("/", 1)[0]
        else:
            video_id = parse_qs(parsed.query).get("v", [""])[0]
            if not video_id:
                path_parts = [part for part in parsed.path.split("/") if part]
                if len(path_parts) >= 2 and path_parts[0] in {"shorts", "live", "embed"}:
                    video_id = path_parts[1]

    if not VIDEO_ID_RE.fullmatch(video_id):
        raise ValueError(f"无法从输入中识别 YouTube video ID: {value}")
    return video_id


def canonical_video_url(video_id: str) -> str:
    return f"{YOUTUBE_BASE_URL}/watch?v={video_id}"


def normalize_language_code(value: str) -> str:
    """Normalize common YouTube/BCP-47 language-code variants for matching."""
    code = value.strip().replace("_", "-").lower()
    aliases = {
        "jp": "ja",
        "zh-cn": "zh-hans",
        "zh-sg": "zh-hans",
        "zh-tw": "zh-hant",
        "zh-hk": "zh-hant",
        "zh-mo": "zh-hant",
    }
    return aliases.get(code, code)


def language_codes_match(preferred: str, available: str) -> bool:
    preferred_code = normalize_language_code(preferred)
    available_code = normalize_language_code(available)
    if preferred_code == available_code:
        return True
    if preferred_code == "zh":
        return available_code == "zh" or available_code.startswith("zh-")
    return available_code.startswith(f"{preferred_code}-") or preferred_code.startswith(
        f"{available_code}-"
    )


def infer_title_language_codes(title: Optional[str]) -> list[str]:
    """Conservatively infer title language only when the writing system is distinctive."""
    if not title:
        return []
    if re.search(r"[\u3040-\u30ff]", title):
        return ["ja"]
    if re.search(r"[\uac00-\ud7af]", title):
        return ["ko"]
    if re.search(r"[\u4e00-\u9fff]", title):
        # Han-only titles can be Chinese or Japanese. Keep both possibilities before
        # the English fallback instead of claiming a certainty the text cannot supply.
        return ["zh-Hans", "zh-Hant", "zh", "ja"]
    if re.search(r"[\u0400-\u04ff]", title):
        return ["ru"]
    if re.search(r"[\u0600-\u06ff]", title):
        return ["ar"]
    if re.search(r"[\u0900-\u097f]", title):
        return ["hi"]
    return []


def build_language_preferences(
    requested_languages: list[str], title: Optional[str]
) -> list[tuple[str, str]]:
    """Build user -> title -> English language priorities without duplicates."""
    preferences: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(code: str, reason: str) -> None:
        normalized = normalize_language_code(code)
        if normalized and normalized not in seen:
            preferences.append((code, reason))
            seen.add(normalized)

    for code in requested_languages:
        add(code, "user_preference")
    for code in infer_title_language_codes(title):
        add(code, "title_language")
    add(ENGLISH_FALLBACK_LANGUAGE, "english_fallback")
    return preferences


def choose_transcript_track(
    tracks: list[Any], preferences: list[tuple[str, str]]
) -> tuple[Any, str, Optional[str]]:
    """Choose a preferred track, then fall back to any available caption track."""
    if not tracks:
        raise RuntimeError("视频没有可访问的字幕轨道")

    for preferred_code, reason in preferences:
        matches = [
            track
            for track in tracks
            if language_codes_match(
                preferred_code, str(get_value(track, "language_code", ""))
            )
        ]
        if matches:
            manual = next(
                (track for track in matches if get_value(track, "is_generated") is False),
                None,
            )
            return manual or matches[0], reason, preferred_code

    # TranscriptList already yields manual tracks before generated tracks. Preserve
    # that quality preference while accepting any language rather than failing.
    return tracks[0], "any_available_track", None


def get_value(item: Any, name: str, default: Any = None) -> Any:
    """兼容新版对象格式和旧版字典格式。"""
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def extract_json_object(page_text: str, markers: Iterable[str]) -> dict[str, Any] | None:
    """从 JavaScript 变量后解析第一个完整 JSON 对象。"""
    decoder = json.JSONDecoder()
    for marker in markers:
        marker_index = page_text.find(marker)
        if marker_index < 0:
            continue
        object_index = page_text.find("{", marker_index + len(marker))
        if object_index < 0:
            continue
        try:
            value, _ = decoder.raw_decode(page_text[object_index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def normalize_youtube_url(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return urljoin(f"{YOUTUBE_BASE_URL}/", value)


def extract_title_date(title: Optional[str]) -> Optional[str]:
    """提取标题中明确写出的日期，但不把它当作上传日期。"""
    if not title:
        return None
    match = re.search(
        r"(?<!\d)(20\d{2})[.\-/年](\d{1,2})[.\-/月](\d{1,2})(?:日)?(?!\d)",
        title,
    )
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3))).isoformat()
    except ValueError:
        return None


def empty_video_metadata(video_id: str) -> dict[str, Any]:
    return {
        "video_id": video_id,
        "canonical_url": canonical_video_url(video_id),
        "title": None,
        "channel_name": None,
        "channel_url": None,
        "upload_date": None,
        "publish_date": None,
        "title_date": None,
        "date_status": "unknown",
        "metadata_sources": [],
        "metadata_errors": [],
    }


def merge_missing(target: dict[str, Any], values: dict[str, Any]) -> bool:
    changed = False
    for key, value in values.items():
        if value not in (None, "") and target.get(key) in (None, ""):
            target[key] = value
            changed = True
    return changed


def parse_video_page(page_text: str) -> dict[str, Any]:
    values: dict[str, Any] = {}
    player_response = extract_json_object(
        page_text,
        (
            "var ytInitialPlayerResponse =",
            "ytInitialPlayerResponse =",
            '"ytInitialPlayerResponse":',
        ),
    )
    if player_response:
        video_details = player_response.get("videoDetails") or {}
        microformat = (
            player_response.get("microformat", {}).get("playerMicroformatRenderer", {})
        )
        channel_id = video_details.get("channelId")
        values.update(
            {
                "title": video_details.get("title"),
                "channel_name": microformat.get("ownerChannelName")
                or video_details.get("author"),
                "channel_url": normalize_youtube_url(microformat.get("ownerProfileUrl"))
                or (
                    f"{YOUTUBE_BASE_URL}/channel/{channel_id}"
                    if channel_id
                    else None
                ),
                "upload_date": microformat.get("uploadDate"),
                "publish_date": microformat.get("publishDate"),
            }
        )

    parser = YouTubeMetaParser()
    parser.feed(page_text)
    meta = parser.values
    merge_missing(
        values,
        {
            "title": meta.get("og:title") or meta.get("title"),
            "channel_name": meta.get("author"),
            "upload_date": meta.get("uploadDate"),
            "publish_date": meta.get("datePublished"),
        },
    )
    return values


def fetch_video_metadata(video_id: str) -> dict[str, Any]:
    """按视频页、oEmbed 的顺序获取元数据；失败不阻断字幕提取。"""
    metadata = empty_video_metadata(video_id)
    try:
        import requests
    except ImportError:
        metadata["metadata_errors"].append(
            "requests: 缺少依赖，无法获取视频元数据"
        )
        return metadata

    headers = {"User-Agent": USER_AGENT}
    try:
        response = requests.get(
            metadata["canonical_url"],
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        page_values = parse_video_page(response.text)
        if merge_missing(metadata, page_values):
            metadata["metadata_sources"].append("youtube_video_page")
        else:
            metadata["metadata_errors"].append(
                "youtube_video_page: 页面可访问，但未解析到元数据"
            )
    except Exception as exc:
        metadata["metadata_errors"].append(f"youtube_video_page: {exc}")

    if not metadata.get("title") or not metadata.get("channel_name"):
        try:
            response = requests.get(
                f"{YOUTUBE_BASE_URL}/oembed",
                params={"url": metadata["canonical_url"], "format": "json"},
                headers=headers,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
            if merge_missing(
                metadata,
                {
                    "title": payload.get("title"),
                    "channel_name": payload.get("author_name"),
                    "channel_url": payload.get("author_url"),
                },
            ):
                metadata["metadata_sources"].append("youtube_oembed")
        except Exception as exc:
            metadata["metadata_errors"].append(f"youtube_oembed: {exc}")

    metadata["title_date"] = extract_title_date(metadata.get("title"))
    if metadata.get("upload_date"):
        metadata["date_status"] = "verified_upload_date"
    elif metadata.get("publish_date"):
        metadata["date_status"] = "verified_publish_date"
    elif metadata.get("title_date"):
        metadata["date_status"] = "title_date_only"
    return metadata


def fetch_segments(
    video_id: str, requested_languages: list[str], title: Optional[str] = None
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """按用户语言、标题语言、英语、任意轨道的顺序获取字幕。"""
    # YouTube 对短时间内重复请求字幕接口较敏感。脚本通常由批量任务
    # 逐视频调用，因此每次提取前都留出一个小的随机间隔，降低触发限流的概率。
    time.sleep(random.uniform(2.0, 6.0))
    try:
        import requests
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as exc:
        raise RuntimeError(
            "缺少依赖，请先运行: python3 -m pip install youtube-transcript-api"
        ) from exc

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    api = YouTubeTranscriptApi(http_client=session)
    tracks = list(api.list(video_id))
    preferences = build_language_preferences(requested_languages, title)
    selected_track, selection_reason, matched_preference = choose_transcript_track(
        tracks, preferences
    )
    transcript = selected_track.fetch()
    metadata = {
        "language": get_value(selected_track, "language")
        or get_value(transcript, "language"),
        "language_code": get_value(selected_track, "language_code")
        or get_value(transcript, "language_code"),
        "is_generated": get_value(selected_track, "is_generated"),
        "selection_reason": selection_reason,
        "matched_preference": matched_preference,
        "requested_languages": requested_languages,
        "title_language_candidates": infer_title_language_codes(title),
    }

    segments = [
        {
            "text": str(get_value(item, "text", "")).strip(),
            "start": float(get_value(item, "start", 0.0)),
            "duration": float(get_value(item, "duration", 0.0)),
        }
        for item in transcript
    ]
    segments = [segment for segment in segments if segment["text"]]
    if not segments:
        raise RuntimeError("字幕接口返回了空内容")

    is_generated = metadata.get("is_generated")
    metadata["track_type"] = (
        "automatic" if is_generated is True else "manual" if is_generated is False else "unknown"
    )
    metadata["segment_count"] = len(segments)
    return segments, metadata


def format_precise_timestamp(seconds: float) -> str:
    """Render a readable timestamp while retaining millisecond precision."""
    milliseconds = max(0, int(round(seconds * 1000)))
    total_seconds, milliseconds = divmod(milliseconds, 1000)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
    return f"{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def yaml_value(value: Any) -> str:
    """Render JSON-compatible YAML scalars without adding a YAML dependency."""
    return json.dumps(value, ensure_ascii=False)


def render_yaml_mapping(name: str, values: dict[str, Any]) -> list[str]:
    lines = [f"{name}:"]
    for key, value in values.items():
        lines.append(f"  {key}: {yaml_value(value)}")
    return lines


def normalize_transcript_text(value: Any) -> str:
    return " ".join(str(value).splitlines()).strip()


def render_markdown(
    video: dict[str, Any], transcript: dict[str, Any], segments: list[dict[str, Any]]
) -> str:
    """Render the sole durable transcript artifact with metadata and precise timing."""
    if video.get("upload_date"):
        date_label = "Upload date"
        date_value = video["upload_date"]
    elif video.get("publish_date"):
        date_label = "Publication date"
        date_value = video["publish_date"]
    elif video.get("title_date"):
        date_label = "Title date (not a verified upload/publication date)"
        date_value = video["title_date"]
    else:
        date_label = "Date"
        date_value = "Unknown"

    lines = [
        "---",
        "schema_version: 1",
        'document_type: "youtube_transcript"',
        *render_yaml_mapping("video", video),
        *render_yaml_mapping("transcript", transcript),
        "---",
        "",
        f"# {video.get('title') or 'Untitled YouTube video'}",
        "",
        f"- **Channel:** {video.get('channel_name') or 'Unknown'}",
        f"- **{date_label}:** {date_value}",
        f"- **Video:** [Open on YouTube]({video['canonical_url']})",
        (
            "- **Caption track:** "
            f"{transcript.get('language') or 'Unknown'} "
            f"({transcript.get('language_code') or 'unknown'}, "
            f"{transcript.get('track_type') or 'unknown'})"
        ),
        f"- **Segments:** {len(segments)}",
        "",
        "## Transcript",
        "",
    ]
    for segment in segments:
        start = float(segment["start"])
        duration = float(segment["duration"])
        seek_seconds = max(0, int(start))
        timestamp = format_precise_timestamp(start)
        url = f"{video['canonical_url']}&t={seek_seconds}s"
        text = normalize_transcript_text(segment["text"])
        lines.append(
            f"- [{timestamp}]({url}) "
            f"`start={start!r}s` `duration={duration!r}s` {text}"
        )
    return "\n".join(lines)


def write_output(content: str, output: Optional[str]) -> None:
    if not output or output == "-":
        sys.stdout.write(content.rstrip("\n") + "\n")
        return
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip("\n") + "\n", encoding="utf-8")
    print(f"已写入: {path}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="从 YouTube URL 获取字幕并生成包含完整元数据和精确时间轴的 Markdown。"
    )
    parser.add_argument("url", help="YouTube URL，例如 https://www.youtube.com/watch?v=...")
    parser.add_argument(
        "-l",
        "--languages",
        default="",
        help=(
            "用户期望的字幕语言，按优先级用逗号分隔；省略时从视频标题语言开始，"
            "随后尝试英语和任意可用字幕"
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Markdown 输出文件路径；省略或传 - 时输出到终端",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        video_id = extract_video_id(args.url)
        languages = [item.strip() for item in args.languages.split(",") if item.strip()]
        video_metadata = fetch_video_metadata(video_id)
        segments, transcript_metadata = fetch_segments(
            video_id, languages, title=video_metadata.get("title")
        )
    except Exception as exc:
        print(f"字幕提取失败: {exc}", file=sys.stderr)
        return 1

    content = render_markdown(video_metadata, transcript_metadata, segments)
    write_output(content, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
