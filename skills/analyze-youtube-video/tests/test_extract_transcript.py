#!/usr/bin/env python3
"""YouTube 字幕提取工具的轻量回归测试。"""

from __future__ import annotations

import unittest
import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
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

    def test_markdown_uses_explicit_unknown_date_label(self) -> None:
        video = extract_transcript.empty_video_metadata("abcdefghijk")
        transcript = {"language": "Chinese", "language_code": "zh", "track_type": "manual"}
        segments = [{"text": "测试", "start": 1.25, "duration": 0.75}]

        rendered = extract_transcript.render_markdown(video, transcript, segments)

        self.assertIn("- **Date:** Unknown", rendered)
        self.assertNotIn("Upload date", rendered)
        self.assertNotIn("Publication date", rendered)


class MarkdownOutputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.video = {
            **extract_transcript.empty_video_metadata("abcdefghijk"),
            "title": "Example video",
            "channel_name": "Example channel",
            "upload_date": "2026-08-22",
            "date_status": "verified_upload_date",
            "metadata_sources": ["youtube_video_page"],
        }
        self.transcript = {
            "language": "Chinese",
            "language_code": "zh-CN",
            "is_generated": False,
            "selection_reason": "user_preference",
            "matched_preference": "zh",
            "requested_languages": ["zh"],
            "title_language_candidates": [],
            "track_type": "manual",
            "segment_count": 1,
        }
        self.segments = [
            {
                "text": "first line\nsecond line",
                "start": 61.23456,
                "duration": 2.34567,
            }
        ]

    def test_markdown_contains_complete_metadata_and_precise_timeline(self) -> None:
        rendered = extract_transcript.render_markdown(
            self.video, self.transcript, self.segments
        )

        self.assertTrue(rendered.startswith("---\nschema_version: 1\n"))
        self.assertIn('document_type: "youtube_transcript"', rendered)
        self.assertIn('  video_id: "abcdefghijk"', rendered)
        self.assertIn('  metadata_sources: ["youtube_video_page"]', rendered)
        self.assertIn('  language_code: "zh-CN"', rendered)
        self.assertIn("  is_generated: false", rendered)
        self.assertIn(
            "[01:01.235](https://www.youtube.com/watch?v=abcdefghijk&t=61s)",
            rendered,
        )
        self.assertIn("`start=61.23456s` `duration=2.34567s`", rendered)
        self.assertIn("first line second line", rendered)

    @patch("extract_transcript.fetch_segments")
    @patch("extract_transcript.fetch_video_metadata")
    def test_cli_writes_one_markdown_artifact(
        self, mock_metadata, mock_segments
    ) -> None:
        mock_metadata.return_value = self.video
        mock_segments.return_value = (self.segments, self.transcript)

        with TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "abcdefghijk.md"
            stderr = StringIO()
            with redirect_stderr(stderr):
                return_code = extract_transcript.main(
                    [
                        "https://www.youtube.com/watch?v=abcdefghijk",
                        "--languages",
                        "zh",
                        "--output",
                        str(output_path),
                    ]
                )

            self.assertEqual(return_code, 0)
            self.assertTrue(output_path.is_file())
            self.assertEqual(list(Path(tmp_dir).iterdir()), [output_path])
            self.assertIn("## Transcript", output_path.read_text(encoding="utf-8"))
            mock_segments.assert_called_once_with(
                "abcdefghijk", ["zh"], title="Example video"
            )

    @patch("extract_transcript.fetch_segments")
    @patch("extract_transcript.fetch_video_metadata")
    def test_cli_auto_names_directory_output_from_verified_upload_date(
        self, mock_metadata, mock_segments
    ) -> None:
        mock_metadata.return_value = self.video
        mock_segments.return_value = (self.segments, self.transcript)

        with TemporaryDirectory() as tmp_dir:
            return_code = extract_transcript.main(
                ["abcdefghijk", "--output", tmp_dir]
            )

            output_path = Path(tmp_dir) / "2026-08-22abcdefghijk.md"
            self.assertEqual(return_code, 0)
            self.assertEqual(list(Path(tmp_dir).iterdir()), [output_path])
            self.assertIn("## Transcript", output_path.read_text(encoding="utf-8"))

    def test_publication_date_and_undated_filename_fallbacks(self) -> None:
        publish_video = {
            **self.video,
            "upload_date": None,
            "publish_date": "2026-08-23",
            "date_status": "verified_publish_date",
        }
        title_date_only = {
            **self.video,
            "upload_date": None,
            "publish_date": None,
            "title_date": "2026-08-24",
            "date_status": "title_date_only",
        }

        self.assertEqual(
            extract_transcript.default_markdown_filename(publish_video),
            "2026-08-23abcdefghijk.md",
        )
        self.assertEqual(
            extract_transcript.default_markdown_filename(title_date_only),
            "undated-abcdefghijk.md",
        )

    def test_invalid_verified_date_falls_back_to_undated(self) -> None:
        invalid_date = {
            **self.video,
            "upload_date": "2026-02-30",
            "date_status": "verified_upload_date",
        }

        self.assertEqual(
            extract_transcript.default_markdown_filename(invalid_date),
            "undated-abcdefghijk.md",
        )

    @patch("extract_transcript.fetch_segments")
    @patch("extract_transcript.fetch_video_metadata")
    def test_cli_defaults_to_markdown_on_stdout(
        self, mock_metadata, mock_segments
    ) -> None:
        mock_metadata.return_value = self.video
        mock_segments.return_value = (self.segments, self.transcript)
        stdout = StringIO()

        with redirect_stdout(stdout):
            return_code = extract_transcript.main(["abcdefghijk"])

        self.assertEqual(return_code, 0)
        self.assertTrue(stdout.getvalue().startswith("---\nschema_version: 1\n"))


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
