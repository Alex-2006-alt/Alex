"""
Tests for the YouTube tools.

The fixture below mimics what YouTube actually serves to an HTTP client:
results live in embedded JSON (ytInitialData), not in anchor tags. The previous
implementation matched `href="/watch?v=..."`, which never appears in that
payload, so every play request silently fell back to a search page.
"""

from unittest.mock import patch, MagicMock

import pytest

from tools.youtube_tools import (
    extract_video_id,
    search_youtube,
    youtube_play,
    youtube_search,
    youtube_control,
)


# Trimmed but structurally faithful slice of a real results page
REAL_PAGE = (
    '<!DOCTYPE html><html><body><script>var ytInitialData = {'
    '"contents":{"twoColumnSearchResultsRenderer":{"primaryContents":'
    '{"sectionListRenderer":{"contents":[{"itemSectionRenderer":{"contents":['
    '{"videoRenderer":{"videoId":"sFMRqxCexDk","title":{"runs":[{"text":"Choo Lo - The Local Train"}]}}},'
    '{"videoRenderer":{"videoId":"AbCdEfGhIjK","title":{"runs":[{"text":"Chulo pt.2"}]}}},'
    '{"videoRenderer":{"videoId":"1234567890a","title":{"runs":[{"text":"Third Result"}]}}}'
    ']}}]}}}};</script></body></html>'
)

# What the old regex expected, and what YouTube never actually returns
LEGACY_ANCHOR_PAGE = '<html><body><a href="/watch?v=dQw4w9WgXcQ">Rickroll</a></body></html>'


def _response(text, status=200):
    resp = MagicMock()
    resp.text = text
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    return resp


class TestExtractVideoId:
    def test_watch_url(self):
        assert extract_video_id("https://www.youtube.com/watch?v=sFMRqxCexDk") == "sFMRqxCexDk"

    def test_watch_url_with_extra_params(self):
        assert extract_video_id("https://www.youtube.com/watch?v=sFMRqxCexDk&t=42s") == "sFMRqxCexDk"

    def test_short_link(self):
        assert extract_video_id("https://youtu.be/sFMRqxCexDk") == "sFMRqxCexDk"

    def test_short_link_without_scheme(self):
        assert extract_video_id("youtu.be/sFMRqxCexDk") == "sFMRqxCexDk"

    def test_bare_id(self):
        assert extract_video_id("sFMRqxCexDk") == "sFMRqxCexDk"

    def test_plain_search_phrase_is_not_an_id(self):
        assert extract_video_id("Chulo song") is None

    def test_eleven_char_phrase_without_spaces_is_ambiguous_but_accepted(self):
        # 11 chars of the id alphabet is by definition indistinguishable
        assert extract_video_id("abcdefghijk") == "abcdefghijk"

    def test_empty(self):
        assert extract_video_id("") is None


class TestSearchParsing:
    @patch("tools.youtube_tools.requests.get")
    def test_parses_ids_and_titles_from_embedded_json(self, mock_get):
        mock_get.return_value = _response(REAL_PAGE)
        results = search_youtube("chulo song", limit=3)

        assert [r["id"] for r in results] == ["sFMRqxCexDk", "AbCdEfGhIjK", "1234567890a"]
        assert results[0]["title"] == "Choo Lo - The Local Train"
        assert results[0]["url"] == "https://www.youtube.com/watch?v=sFMRqxCexDk"

    @patch("tools.youtube_tools.requests.get")
    def test_respects_the_limit(self, mock_get):
        mock_get.return_value = _response(REAL_PAGE)
        assert len(search_youtube("q", limit=2)) == 2

    @patch("tools.youtube_tools.requests.get")
    def test_duplicate_ids_are_collapsed(self, mock_get):
        dupe = '"videoId":"sFMRqxCexDk"' * 5
        mock_get.return_value = _response(dupe)
        assert len(search_youtube("q", limit=5)) == 1

    @patch("tools.youtube_tools.requests.get")
    def test_page_with_no_results_returns_empty(self, mock_get):
        mock_get.return_value = _response("<html>nothing here</html>")
        assert search_youtube("q") == []

    @patch("tools.youtube_tools.requests.get")
    def test_the_old_anchor_markup_is_not_what_we_rely_on(self, mock_get):
        """Regression marker: the previous regex only worked on this fixture."""
        mock_get.return_value = _response(LEGACY_ANCHOR_PAGE)
        assert search_youtube("q") == []


class TestYoutubePlay:
    @patch("tools.youtube_tools.focus_browser")
    @patch("tools.youtube_tools.open_url", return_value=True)
    @patch("tools.youtube_tools.requests.get")
    def test_plays_the_first_result(self, mock_get, mock_open, mock_focus):
        mock_get.return_value = _response(REAL_PAGE)

        result = youtube_play({"query": "chulo song"})

        assert result.success is True
        mock_open.assert_called_once_with("https://www.youtube.com/watch?v=sFMRqxCexDk")
        assert result.data["played"] is True
        assert result.data["video_id"] == "sFMRqxCexDk"
        assert "Choo Lo" in result.message

    @patch("tools.youtube_tools.focus_browser")
    @patch("tools.youtube_tools.open_url", return_value=True)
    @patch("tools.youtube_tools.requests.get")
    def test_direct_url_skips_the_search(self, mock_get, mock_open, mock_focus):
        result = youtube_play({"query": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})

        assert result.success is True
        assert not mock_get.called, "a direct URL should not trigger a search"
        mock_open.assert_called_once_with("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    @patch("tools.youtube_tools.focus_browser")
    @patch("tools.youtube_tools.open_url", return_value=True)
    @patch("tools.youtube_tools.requests.get")
    def test_the_browser_is_brought_to_the_front(self, mock_get, mock_open, mock_focus):
        mock_get.return_value = _response(REAL_PAGE)
        youtube_play({"query": "chulo song"})
        mock_focus.assert_called_with("YouTube")

    @patch("tools.youtube_tools.focus_browser")
    @patch("tools.youtube_tools.open_url", return_value=True)
    @patch("tools.youtube_tools.requests.get")
    def test_network_failure_falls_back_honestly(self, mock_get, mock_open, mock_focus):
        """The fallback must not claim it is playing something."""
        mock_get.side_effect = Exception("Connection error")

        result = youtube_play({"query": "some query"})

        assert result.success is True
        mock_open.assert_called_once_with(
            "https://www.youtube.com/results?search_query=some+query"
        )
        assert result.data["played"] is False
        assert "couldn't pick a video" in result.message.lower()
        assert "playing" not in result.message.lower()

    @patch("tools.youtube_tools.focus_browser")
    @patch("tools.youtube_tools.open_url", return_value=False)
    @patch("tools.youtube_tools.requests.get")
    def test_browser_failure_is_reported(self, mock_get, mock_open, mock_focus):
        mock_get.return_value = _response(REAL_PAGE)
        assert youtube_play({"query": "chulo"}).success is False

    def test_empty_query_rejected(self):
        assert youtube_play({"query": ""}).success is False


class TestYoutubeSearch:
    @patch("tools.youtube_tools.requests.get")
    def test_lists_results(self, mock_get):
        mock_get.return_value = _response(REAL_PAGE)
        result = youtube_search({"query": "chulo", "limit": 2})
        assert result.success is True
        assert "Choo Lo" in result.message
        assert len(result.data["results"]) == 2

    @patch("tools.youtube_tools.requests.get")
    def test_no_results_is_a_failure(self, mock_get):
        mock_get.return_value = _response("<html></html>")
        assert youtube_search({"query": "zzz"}).success is False

    def test_empty_query_rejected(self):
        assert youtube_search({"query": "  "}).success is False


class TestYoutubeControl:
    @patch("tools.youtube_tools._send_youtube_keys", return_value=True)
    def test_play_pause_sends_k(self, mock_send):
        assert youtube_control({"action": "play_pause"}).success is True
        mock_send.assert_called_once_with(["k"])

    @patch("tools.youtube_tools._send_youtube_keys", return_value=True)
    def test_next_sends_shift_n(self, mock_send):
        youtube_control({"action": "next"})
        mock_send.assert_called_once_with(["shift", "n"])

    @patch("tools.youtube_tools._send_youtube_keys", return_value=True)
    def test_action_names_are_normalised(self, mock_send):
        assert youtube_control({"action": "Volume Up"}).success is True
        mock_send.assert_called_once_with(["up"])

    def test_unknown_action_rejected(self):
        result = youtube_control({"action": "teleport"})
        assert result.success is False
        assert "play_pause" in result.error

    @patch("tools.youtube_tools._send_youtube_keys", return_value=False)
    def test_no_youtube_window_is_reported_not_pretended(self, mock_send):
        result = youtube_control({"action": "next"})
        assert result.success is False
        assert "couldn't find" in result.message.lower()

    @patch("tools.youtube_tools.focus_browser", return_value=False)
    def test_keys_are_not_sent_when_no_window_is_focused(self, mock_focus):
        """A stray 'k' must never land in whatever the user is typing in."""
        with patch("pyautogui.press") as mock_press:
            youtube_control({"action": "play_pause"})
            assert not mock_press.called
