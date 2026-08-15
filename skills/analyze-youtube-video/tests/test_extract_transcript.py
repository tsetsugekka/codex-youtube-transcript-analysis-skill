#!/usr/bin/env python3
"""YouTube 字幕提取工具的轻量回归测试。"""

from __future__ import annotations

import unittest
import sys
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

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


class FakeTrack:
    def __init__(
        self,
        language_code: str,
        *,
        language: str = "Example",
        is_generated: bool = False,
    ) -> None:
        self.language_code = language_code
        self.language = language
        self.is_generated = is_generated

    def fetch(self) -> list[dict]:
        return [{"text": "example", "start": 1.25, "duration": 0.75}]


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
        for request_call in mock_get.call_args_list:
            self.assertEqual(
                request_call.kwargs["headers"],
                {"User-Agent": extract_transcript.USER_AGENT},
            )
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


class LanguageSelectionTests(unittest.TestCase):
    def test_priority_is_user_then_title_then_english(self) -> None:
        preferences = extract_transcript.build_language_preferences(
            ["zh-Hans"], "日本市場の振り返り"
        )

        self.assertEqual(
            preferences,
            [
                ("zh-Hans", "user_preference"),
                ("ja", "title_language"),
                ("en", "english_fallback"),
            ],
        )

    def test_title_language_wins_when_user_language_is_unavailable(self) -> None:
        tracks = [
            FakeTrack("en", language="English"),
            FakeTrack("ja", language="Japanese", is_generated=True),
        ]
        preferences = extract_transcript.build_language_preferences(
            ["zh-Hans"], "日本市場の振り返り"
        )

        selected, reason, matched = extract_transcript.choose_transcript_track(
            tracks, preferences
        )

        self.assertEqual(selected.language_code, "ja")
        self.assertEqual(reason, "title_language")
        self.assertEqual(matched, "ja")

    def test_english_precedes_any_other_available_language(self) -> None:
        tracks = [FakeTrack("es"), FakeTrack("en")]
        preferences = extract_transcript.build_language_preferences(["ja"], None)

        selected, reason, matched = extract_transcript.choose_transcript_track(
            tracks, preferences
        )

        self.assertEqual(selected.language_code, "en")
        self.assertEqual(reason, "english_fallback")
        self.assertEqual(matched, "en")

    def test_any_available_track_is_used_instead_of_failing(self) -> None:
        tracks = [FakeTrack("es", language="Spanish")]
        preferences = extract_transcript.build_language_preferences(["ja"], None)

        selected, reason, matched = extract_transcript.choose_transcript_track(
            tracks, preferences
        )

        self.assertEqual(selected.language_code, "es")
        self.assertEqual(reason, "any_available_track")
        self.assertIsNone(matched)

    @patch("youtube_transcript_api.YouTubeTranscriptApi")
    @patch("requests.Session")
    @patch("extract_transcript.time.sleep")
    def test_transcript_api_receives_custom_user_agent_session(
        self, _mock_sleep, mock_session_class, mock_api_class
    ) -> None:
        session = MagicMock()
        mock_session_class.return_value = session
        api = MagicMock()
        api.list.return_value = [FakeTrack("ja", language="Japanese")]
        mock_api_class.return_value = api

        segments, metadata = extract_transcript.fetch_segments(
            "abcdefghijk", ["ja"], title="日本市場"
        )

        session.headers.update.assert_called_once_with(
            {"User-Agent": extract_transcript.USER_AGENT}
        )
        mock_api_class.assert_called_once_with(http_client=session)
        api.list.assert_called_once_with("abcdefghijk")
        self.assertEqual(segments[0]["text"], "example")
        self.assertEqual(metadata["selection_reason"], "user_preference")


if __name__ == "__main__":
    unittest.main()
