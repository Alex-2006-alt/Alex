"""
Tests for web tools — URL opening, browser focus, and the page-title hint.
"""

from unittest.mock import patch, MagicMock

import pytest

from tools.web_tools import open_url, web_open, _page_hint


class TestOpenUrl:
    @patch("tools.web_tools.allow_foreground_for_any_process")
    @patch("tools.web_tools.os.startfile", create=True)
    def test_uses_startfile_first(self, mock_startfile, mock_allow):
        assert open_url("https://example.com") is True
        mock_startfile.assert_called_once_with("https://example.com")

    @patch("tools.web_tools.allow_foreground_for_any_process")
    @patch("tools.web_tools.os.startfile", create=True)
    def test_asks_windows_to_release_the_foreground_lock(self, mock_startfile, mock_allow):
        """Without this the new tab opens behind the ALEX window."""
        open_url("https://example.com")
        assert mock_allow.called

    @patch("tools.web_tools.allow_foreground_for_any_process")
    @patch("tools.web_tools.subprocess.Popen")
    @patch("tools.web_tools.os.startfile", create=True, side_effect=OSError("nope"))
    def test_falls_back_to_cmd_start_with_an_empty_title(self, mock_sf, mock_popen, mock_allow):
        """
        cmd's `start` treats a lone quoted argument as the window title, so the
        empty "" is required or the URL is silently swallowed.
        """
        assert open_url("https://example.com") is True
        args = mock_popen.call_args[0][0]
        assert args == ["cmd", "/c", "start", "", "https://example.com"]

    @patch("tools.web_tools.allow_foreground_for_any_process")
    @patch("tools.web_tools.webbrowser.open", return_value=True)
    @patch("tools.web_tools.subprocess.Popen", side_effect=OSError("nope"))
    @patch("tools.web_tools.os.startfile", create=True, side_effect=OSError("nope"))
    def test_falls_back_to_webbrowser_last(self, mock_sf, mock_popen, mock_wb, mock_allow):
        assert open_url("https://example.com") is True
        mock_wb.assert_called_once_with("https://example.com")

    @patch("tools.web_tools.allow_foreground_for_any_process")
    @patch("tools.web_tools.webbrowser.open", return_value=False)
    @patch("tools.web_tools.subprocess.Popen", side_effect=OSError("nope"))
    @patch("tools.web_tools.os.startfile", create=True, side_effect=OSError("nope"))
    def test_reports_failure_when_every_method_fails(self, mock_sf, mock_popen, mock_wb, mock_allow):
        assert open_url("https://example.com") is False


class TestPageHint:
    @pytest.mark.parametrize("url,expected", [
        ("https://www.youtube.com/watch?v=abc", "YouTube"),
        ("https://youtu.be/abc", "YouTube"),
        ("https://duckduckgo.com/?q=x", "DuckDuckGo"),
        ("https://github.com/foo", "GitHub"),
        ("https://example.com/page", "Example"),
    ])
    def test_hint_from_host(self, url, expected):
        assert _page_hint(url) == expected

    def test_garbage_url_does_not_raise(self):
        assert isinstance(_page_hint("not a url"), str)


class TestWebOpen:
    @patch("tools.web_tools.focus_browser")
    @patch("tools.web_tools.open_url", return_value=True)
    def test_focuses_by_default(self, mock_open, mock_focus):
        """
        Regression: focus used to require the LLM passing focus_title, which it
        never did, so every tab opened behind the ALEX window.
        """
        result = web_open({"url": "https://www.youtube.com"})
        assert result.success is True
        mock_focus.assert_called_once_with("YouTube")

    @patch("tools.web_tools.focus_browser")
    @patch("tools.web_tools.open_url", return_value=True)
    def test_focus_can_be_turned_off(self, mock_open, mock_focus):
        web_open({"url": "https://example.com", "focus": False})
        assert not mock_focus.called

    @patch("tools.web_tools.focus_browser")
    @patch("tools.web_tools.open_url", return_value=True)
    def test_scheme_is_added(self, mock_open, mock_focus):
        web_open({"url": "example.com"})
        mock_open.assert_called_once_with("https://example.com")

    @patch("tools.web_tools.focus_browser")
    @patch("tools.web_tools.open_url", return_value=False)
    def test_failure_to_open_is_reported(self, mock_open, mock_focus):
        assert web_open({"url": "https://example.com"}).success is False

    def test_missing_url_rejected(self):
        assert web_open({}).success is False
