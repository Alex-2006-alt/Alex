import pytest
from unittest.mock import patch, MagicMock
from tools.web_tools import youtube_play, ToolResult

@patch("tools.web_tools.requests.get")
@patch("tools.web_tools.webbrowser.open")
@patch("tools.web_tools.focus_window")
def test_youtube_play_success(mock_focus, mock_open, mock_get):
    """Test playing a YouTube video successfully finds the ID and opens it."""
    
    mock_response = MagicMock()
    mock_response.text = '<html><body><a href="/watch?v=dQw4w9WgXcQ">Rickroll</a></body></html>'
    mock_get.return_value = mock_response

    result = youtube_play({"query": "never gonna give you up"})

    assert result.success is True
    assert mock_get.called
    mock_open.assert_called_with("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    mock_focus.assert_called_with("YouTube", timeout=3.0)
    assert "Playing" in result.message

@patch("tools.web_tools.requests.get")
@patch("tools.web_tools.webbrowser.open")
@patch("tools.web_tools.focus_window")
def test_youtube_play_fallback(mock_focus, mock_open, mock_get):
    """Test youtube_play fallback to search URL if scrape fails."""
    
    mock_get.side_effect = Exception("Connection error")

    result = youtube_play({"query": "some query"})

    assert result.success is True
    assert mock_get.called
    # quote_plus turns space to +
    mock_open.assert_called_with("https://www.youtube.com/results?search_query=some+query")
    mock_focus.assert_called_with("YouTube", timeout=3.0)
    assert "Opened YouTube search" in result.message
