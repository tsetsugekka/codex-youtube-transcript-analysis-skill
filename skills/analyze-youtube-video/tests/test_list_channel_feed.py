#!/usr/bin/env python3
"""Regression tests for the YouTube channel RSS helper."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import list_channel_feed


SAMPLE_FEED = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns="http://www.w3.org/2005/Atom">
  <title>Example Channel</title>
  <yt:channelId>UCAAAAAAAAAAAAAAAAAAAAAA</yt:channelId>
  <entry>
    <yt:videoId>abcdefghijk</yt:videoId>
    <yt:channelId>UCAAAAAAAAAAAAAAAAAAAAAA</yt:channelId>
    <title>Market recap</title>
    <published>2026-08-22T20:15:00+00:00</published>
    <updated>2026-08-22T20:30:00+00:00</updated>
    <author><name>Example Channel</name></author>
  </entry>
</feed>
"""


class ChannelIdTests(unittest.TestCase):
    def test_accepts_raw_channel_id(self) -> None:
        channel_id = "UCAAAAAAAAAAAAAAAAAAAAAA"
        self.assertEqual(list_channel_feed.parse_channel_id(channel_id), channel_id)

    def test_accepts_official_channel_url(self) -> None:
        channel_id = "UCAAAAAAAAAAAAAAAAAAAAAA"
        url = f"https://www.youtube.com/channel/{channel_id}?view_as=subscriber"
        self.assertEqual(list_channel_feed.parse_channel_id(url), channel_id)

    def test_rejects_handle_until_resolved(self) -> None:
        with self.assertRaises(ValueError):
            list_channel_feed.parse_channel_id("https://www.youtube.com/@example")


class FeedTests(unittest.TestCase):
    def test_parse_feed_preserves_publication_and_update_times(self) -> None:
        result = list_channel_feed.parse_feed(
            SAMPLE_FEED, "UCAAAAAAAAAAAAAAAAAAAAAA"
        )

        self.assertEqual(result["entry_count"], 1)
        self.assertEqual(result["channel_id"], "UCAAAAAAAAAAAAAAAAAAAAAA")
        self.assertEqual(result["entries"][0]["video_id"], "abcdefghijk")
        self.assertEqual(
            result["entries"][0]["published"], "2026-08-22T20:15:00+00:00"
        )
        self.assertEqual(
            result["entries"][0]["url"],
            "https://www.youtube.com/watch?v=abcdefghijk",
        )

    @patch("list_channel_feed.urllib.request.urlopen")
    def test_fetch_uses_one_request_with_headers(self, mock_urlopen) -> None:
        response = MagicMock()
        response.read.return_value = SAMPLE_FEED.encode("utf-8")
        response.__enter__.return_value = response
        response.__exit__.return_value = None
        mock_urlopen.return_value = response

        result = list_channel_feed.fetch_channel_feed(
            "UCAAAAAAAAAAAAAAAAAAAAAA", timeout=7.5
        )

        mock_urlopen.assert_called_once()
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(mock_urlopen.call_args.kwargs["timeout"], 7.5)
        self.assertEqual(request.get_header("User-agent"), list_channel_feed.USER_AGENT)
        self.assertEqual(result["entry_count"], 1)
        self.assertIn("fetched_at", result)

    def test_invalid_root_channel_id_does_not_replace_requested_id(self) -> None:
        malformed_root = SAMPLE_FEED.replace(
            "<yt:channelId>UCAAAAAAAAAAAAAAAAAAAAAA</yt:channelId>",
            "<yt:channelId>AAAAAAAAAAAAAAAAAAAAAA</yt:channelId>",
            1,
        )

        result = list_channel_feed.parse_feed(
            malformed_root, "UCAAAAAAAAAAAAAAAAAAAAAA"
        )

        self.assertEqual(result["channel_id"], "UCAAAAAAAAAAAAAAAAAAAAAA")


if __name__ == "__main__":
    unittest.main()
