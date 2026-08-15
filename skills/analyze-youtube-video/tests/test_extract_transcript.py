#!/usr/bin/env python3
"""YouTube 字幕提取工具的轻量回归测试。"""

from __future__ import annotations

import unittest
import sys
from pathlib import Path
from typing import Optional
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import extract_transcript


class FakeResponse:
    def __init__(self, text: str = "", payload: Optional[dict] = None) -> None:
        self.text = text
        self.payload = payload or {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class MetadataFallbackTests(unittest.TestCase):
    @patch("requests.get")
    def test_video_page_then_oembed_and_title_date_only(self, mock_get) -> None:
        mock_get.side_effect = [
            FakeResponse("<html><head></head><body></body></html>"),
            FakeResponse(
                payload={
                    "title": "市场复盘（2026.08.14）",
                    "author_name": "示例频道",
                    "author_url": "https://www.youtube.com/@example",
                }
            ),
        ]

        metadata = extract_transcript.fetch_video_metadata("abcdefghijk")

        self.assertEqual(mock_get.call_count, 2)
        self.assertIn("/watch?v=abcdefghijk", mock_get.call_args_list[0].args[0])
        self.assertTrue(mock_get.call_args_list[1].args[0].endswith("/oembed"))
        self.assertEqual(metadata["metadata_sources"], ["youtube_oembed"])
        self.assertIsNone(metadata["upload_date"])
        self.assertIsNone(metadata["publish_date"])
        self.assertEqual(metadata["title_date"], "2026-08-14")
        self.assertEqual(metadata["date_status"], "title_date_only")

    @patch("requests.get")
    def test_date_remains_unknown_when_no_source_confirms_it(self, mock_get) -> None:
        mock_get.side_effect = [
            FakeResponse("<html><head></head><body></body></html>"),
            FakeResponse(payload={"title": "市场复盘", "author_name": "示例频道"}),
        ]

        metadata = extract_transcript.fetch_video_metadata("abcdefghijk")

        self.assertIsNone(metadata["title_date"])
        self.assertEqual(metadata["date_status"], "unknown")

    def test_readable_text_uses_explicit_unknown_date_label(self) -> None:
        video = extract_transcript.empty_video_metadata("abcdefghijk")
        transcript = {"language": "Chinese", "language_code": "zh", "track_type": "manual"}
        segments = [{"text": "测试", "start": 1.25, "duration": 0.75}]

        rendered = extract_transcript.render_readable_text(video, transcript, segments)

        self.assertIn("日期未知", rendered)
        self.assertNotIn("上传日期", rendered)
        self.assertNotIn("发布日期", rendered)


if __name__ == "__main__":
    unittest.main()
