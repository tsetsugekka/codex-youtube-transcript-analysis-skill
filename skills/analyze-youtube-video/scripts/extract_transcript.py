#!/usr/bin/env python3
"""从 YouTube URL 获取字幕、字幕轨道信息和基础视频元数据。"""

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
DEFAULT_LANGUAGES = ("zh-Hans", "zh-Hant", "zh", "en", "ja")
YOUTUBE_BASE_URL = "https://www.youtube.com"
REQUEST_TIMEOUT_SECONDS = 15
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
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

    headers = {"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}
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
    video_id: str, languages: list[str]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """获取字幕片段；优先使用新版实例 API，同时兼容旧版静态 API。"""
    # YouTube 对短时间内重复请求字幕接口较敏感。脚本通常由批量任务
    # 逐视频调用，因此每次提取前都留出一个小的随机间隔，降低触发限流的概率。
    time.sleep(random.uniform(2.0, 6.0))
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as exc:
        raise RuntimeError(
            "缺少依赖，请先运行: python3 -m pip install youtube-transcript-api"
        ) from exc

    api = YouTubeTranscriptApi()
    if hasattr(api, "fetch"):
        transcript = api.fetch(video_id, languages=languages)
        metadata = {
            "language": get_value(transcript, "language"),
            "language_code": get_value(transcript, "language_code"),
            "is_generated": get_value(transcript, "is_generated"),
        }
    else:
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=languages)
        metadata = {"language": None, "language_code": None, "is_generated": None}

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


def format_timestamp(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"


def render_text(segments: Iterable[dict[str, Any]], timestamps: bool) -> str:
    if timestamps:
        return "\n".join(
            f"[{format_timestamp(segment['start'])}] {segment['text']}"
            for segment in segments
        )
    return "\n".join(segment["text"] for segment in segments)


def render_readable_text(
    video: dict[str, Any], transcript: dict[str, Any], segments: list[dict[str, Any]]
) -> str:
    if video.get("upload_date"):
        date_line = f"上传日期: {video['upload_date']}"
    elif video.get("publish_date"):
        date_line = f"发布日期: {video['publish_date']}"
    elif video.get("title_date"):
        date_line = f"标题日期: {video['title_date']}（不是已验证的上传/发布日期）"
    else:
        date_line = "日期未知"

    lines = [
        f"标题: {video.get('title') or '未知'}",
        f"频道: {video.get('channel_name') or '未知'}",
        date_line,
        f"视频: {video['canonical_url']}",
        (
            "字幕轨道: "
            f"{transcript.get('language') or '未知'} "
            f"({transcript.get('language_code') or 'unknown'}, "
            f"{transcript.get('track_type') or 'unknown'})"
        ),
        f"字幕片段: {len(segments)}",
        "",
        "---",
        "",
        render_text(segments, timestamps=True),
    ]
    return "\n".join(lines)


def write_output(content: str, output: Optional[str]) -> None:
    if not output or output == "-":
        print(content)
        return
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content + "\n", encoding="utf-8")
    print(f"已写入: {path}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="从 YouTube URL 获取字幕、字幕轨道信息和基础视频元数据。"
    )
    parser.add_argument("url", help="YouTube URL，例如 https://www.youtube.com/watch?v=...")
    parser.add_argument(
        "-l",
        "--languages",
        default=",".join(DEFAULT_LANGUAGES),
        help="按优先级排列的语言代码，逗号分隔；默认: %(default)s",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=("text", "json"),
        default="text",
        help="主输出格式，默认 text",
    )
    parser.add_argument(
        "-t",
        "--timestamps",
        action="store_true",
        help="纯文本主输出时在每行前添加时间戳",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="主输出文件路径；省略或传 - 时输出到终端",
    )
    parser.add_argument(
        "--text-output",
        help="JSON 主输出时，同时写出带元数据与时间戳的阅读用文本",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.text_output and args.format != "json":
        parser.error("--text-output 只能与 --format json 一起使用")

    try:
        video_id = extract_video_id(args.url)
        languages = [item.strip() for item in args.languages.split(",") if item.strip()]
        if not languages:
            parser.error("--languages 不能是空值")
        segments, transcript_metadata = fetch_segments(video_id, languages)
        video_metadata = fetch_video_metadata(video_id)
    except Exception as exc:
        print(f"字幕提取失败: {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        content = json.dumps(
            {
                "schema_version": 1,
                "video": video_metadata,
                "transcript": {
                    **transcript_metadata,
                    "segments": segments,
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    else:
        content = render_text(segments, timestamps=args.timestamps)

    write_output(content, args.output)
    if args.text_output:
        write_output(
            render_readable_text(video_metadata, transcript_metadata, segments),
            args.text_output,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
