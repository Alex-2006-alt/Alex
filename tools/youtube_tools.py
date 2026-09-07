"""
ALEX — YouTube Tools
Search, play, and control YouTube without an API key.

Resolution works by pulling video ids out of the JSON that YouTube embeds in
its search results page. The obvious approach — matching href="/watch?v=..." —
does not work: modern YouTube renders results from ytInitialData, and that
anchor markup is never present in the HTML served to a plain HTTP client.
"""

import re
import time
from urllib.parse import quote_plus, urlparse, parse_qs

import requests

from core.tool_registry import tool, ToolResult, SafetyLevel
from utils.logger import log
from utils.window_utils import focus_browser
from tools.web_tools import open_url

SEARCH_URL = "https://www.youtube.com/results?search_query={}"
WATCH_URL = "https://www.youtube.com/watch?v={}"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Video ids are exactly 11 characters of [A-Za-z0-9_-]
_VIDEO_ID_RE = re.compile(r'"videoId":"([A-Za-z0-9_-]{11})"')
_TITLE_RE = re.compile(r'"title":\{"runs":\[\{"text":"(.*?)"\}\]')
_BARE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def extract_video_id(target: str) -> str | None:
    """Pull a video id out of a watch URL, a youtu.be link, or a bare id."""
    if not target:
        return None

    target = target.strip()

    if _BARE_ID_RE.match(target):
        return target

    if "youtu" in target:
        parsed = urlparse(target if "//" in target else "https://" + target)
        if "youtu.be" in parsed.netloc:
            candidate = parsed.path.lstrip("/").split("/")[0]
            if _BARE_ID_RE.match(candidate):
                return candidate
        ids = parse_qs(parsed.query).get("v")
        if ids and _BARE_ID_RE.match(ids[0]):
            return ids[0]

    return None


def search_youtube(query: str, limit: int = 5) -> list[dict]:
    """
    Return up to `limit` {id, title, url} results for a query.

    Raises on network failure so callers can decide what to do; returns an
    empty list when the page loads but nothing could be parsed.
    """
    resp = requests.get(SEARCH_URL.format(quote_plus(query)), headers=_HEADERS, timeout=12)
    resp.raise_for_status()

    ids = _VIDEO_ID_RE.findall(resp.text)
    titles = _TITLE_RE.findall(resp.text)

    results = []
    seen = set()
    for index, video_id in enumerate(ids):
        if video_id in seen:
            continue
        seen.add(video_id)
        title = titles[index] if index < len(titles) else ""
        # Titles come out of JSON with escaped unicode; decode them best-effort
        try:
            title = title.encode().decode("unicode_escape")
        except Exception:
            pass
        results.append({"id": video_id, "title": title, "url": WATCH_URL.format(video_id)})
        if len(results) >= limit:
            break

    return results


@tool(
    name="youtube_search",
    description=(
        "Search YouTube and return the top matching videos with their titles. "
        "Use when the user wants to see options rather than play something immediately."
    ),
    parameters={
        "query": {"type": "string", "description": "What to search for", "required": True},
        "limit": {"type": "integer", "description": "How many results (default 5)", "required": False},
    },
    category="web",
    examples=[
        "youtube_search({'query': 'lofi hip hop', 'limit': 3})",
    ],
)
def youtube_search(params: dict) -> ToolResult:
    query = (params.get("query") or "").strip()
    if not query:
        return ToolResult(success=False, error="No search query provided")

    try:
        results = search_youtube(query, int(params.get("limit", 5)))
    except Exception as e:
        log.error(f"YouTube search failed for '{query}': {e}")
        return ToolResult(success=False, error=f"Couldn't reach YouTube: {e}")

    if not results:
        return ToolResult(success=False, error=f"No YouTube results found for '{query}'")

    lines = [f"Top YouTube results for '{query}':"]
    lines += [f"{i}. {r['title']}" for i, r in enumerate(results, 1)]

    return ToolResult(success=True, message="\n".join(lines), data={"query": query, "results": results})


@tool(
    name="youtube_play",
    description=(
        "Play a video on YouTube. Give it a search phrase (song or video name) and it "
        "opens the first matching video playing, or give it a YouTube URL or video id "
        "to play that exact video. This is the right tool for 'play X', "
        "'play X on YouTube', or 'put on some X'."
    ),
    parameters={
        "query": {"type": "string", "description": "Song/video to search for, or a YouTube URL or video id", "required": True},
        "fullscreen": {"type": "boolean", "description": "Open the video fullscreen (default false)", "required": False},
    },
    category="web",
    examples=[
        "youtube_play({'query': 'Choo Lo The Local Train'})",
        "youtube_play({'query': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'})",
    ],
)
def youtube_play(params: dict) -> ToolResult:
    query = (params.get("query") or "").strip()
    if not query:
        return ToolResult(success=False, error="No video specified")

    # 1. Already a URL or id? Play it directly.
    video_id = extract_video_id(query)
    title = None

    # 2. Otherwise resolve the search to the top result.
    if not video_id:
        try:
            results = search_youtube(query, limit=1)
            if results:
                video_id = results[0]["id"]
                title = results[0]["title"]
        except Exception as e:
            log.warning(f"YouTube search failed for '{query}': {e}")

    # 3. Nothing resolved — open the results page and say so honestly.
    if not video_id:
        search_url = SEARCH_URL.format(quote_plus(query))
        opened = open_url(search_url)
        focus_browser("YouTube")
        if not opened:
            return ToolResult(success=False, error=f"Couldn't open the browser for '{query}'")
        return ToolResult(
            success=True,
            message=f"I couldn't pick a video automatically, so I've opened the YouTube search for '{query}' — take your pick.",
            data={"query": query, "video_id": None, "url": search_url, "played": False},
        )

    url = WATCH_URL.format(video_id)
    if not open_url(url):
        return ToolResult(success=False, error=f"Couldn't open the browser for '{query}'")

    focus_browser("YouTube")
    log.info(f"▶️ Playing YouTube video: {url} ({title or 'direct'})")

    if params.get("fullscreen"):
        _send_youtube_keys(["f"], settle=2.5)

    spoken = f"Playing {title}." if title else "Playing that on YouTube."
    return ToolResult(
        success=True,
        message=spoken,
        data={"query": query, "video_id": video_id, "title": title, "url": url, "played": True},
    )


# ─── Playback control ────────────────────────────────────────────────────────

# YouTube's own keyboard shortcuts, sent to the focused browser window.
_CONTROLS = {
    "play": ["k"],
    "pause": ["k"],
    "play_pause": ["k"],
    "toggle": ["k"],
    "next": ["shift", "n"],
    "previous": ["shift", "p"],
    "mute": ["m"],
    "unmute": ["m"],
    "fullscreen": ["f"],
    "captions": ["c"],
    "forward": ["l"],
    "back": ["j"],
    "volume_up": ["up"],
    "volume_down": ["down"],
}


def _send_youtube_keys(keys: list[str], settle: float = 0.4) -> bool:
    """
    Send a key or hotkey to the focused YouTube window.

    Refuses unless a YouTube window is actually in front — otherwise a stray
    'k' or 'j' lands in whatever the user happens to be typing in.
    """
    if not focus_browser("YouTube", timeout=4.0):
        return False

    try:
        import pyautogui
    except Exception as e:
        log.error(f"pyautogui unavailable: {e}")
        return False

    time.sleep(settle)
    try:
        if len(keys) == 1:
            pyautogui.press(keys[0])
        else:
            pyautogui.hotkey(*keys)
        return True
    except Exception as e:
        log.error(f"Failed to send keys {keys}: {e}")
        return False


@tool(
    name="youtube_control",
    description=(
        "Control whatever is playing on YouTube: pause, resume, skip to the next or "
        "previous video, mute, go fullscreen, seek, or change volume."
    ),
    parameters={
        "action": {
            "type": "string",
            "description": "play_pause, next, previous, mute, fullscreen, captions, forward, back, volume_up, volume_down",
            "required": True,
        },
    },
    category="web",
    examples=[
        "youtube_control({'action': 'play_pause'})",
        "youtube_control({'action': 'next'})",
    ],
)
def youtube_control(params: dict) -> ToolResult:
    action = (params.get("action") or "").strip().lower().replace(" ", "_").replace("-", "_")

    keys = _CONTROLS.get(action)
    if not keys:
        return ToolResult(
            success=False,
            error=f"Unknown action '{action}'. Try one of: {', '.join(sorted(_CONTROLS))}",
        )

    if not _send_youtube_keys(keys):
        return ToolResult(
            success=False,
            message="I couldn't find a YouTube window to control — is something playing?",
            error="No focused YouTube window",
        )

    friendly = {
        "play_pause": "Toggled playback.",
        "play": "Toggled playback.",
        "pause": "Toggled playback.",
        "toggle": "Toggled playback.",
        "next": "Skipped to the next video.",
        "previous": "Went back to the previous video.",
        "mute": "Toggled mute.",
        "unmute": "Toggled mute.",
        "fullscreen": "Toggled fullscreen.",
        "captions": "Toggled captions.",
        "forward": "Skipped forward 10 seconds.",
        "back": "Skipped back 10 seconds.",
        "volume_up": "Turned it up.",
        "volume_down": "Turned it down.",
    }
    return ToolResult(success=True, message=friendly.get(action, f"Done: {action}"))
