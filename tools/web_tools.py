"""
ALEX — Web Tools
Web search, URL opening, and page scraping capabilities.
"""

import os
import subprocess
import webbrowser
from urllib.parse import quote_plus, urlparse

import requests

from core.tool_registry import tool, ToolResult, SafetyLevel
from utils.logger import log
from utils.window_utils import focus_browser, allow_foreground_for_any_process


def open_url(url: str) -> bool:
    """
    Open a URL in the default browser, reliably from any thread.

    ``webbrowser.open()`` can silently fail when called from Flask worker
    threads on Windows, so we try three progressively cruder methods:
      1. ``os.startfile`` (Windows-native, works from any thread)
      2. ``cmd /c start`` (shell-level fallback)
      3. ``webbrowser.open`` (standard library last resort)

    Also asks Windows to let the browser take the foreground, so the new tab
    lands in front of ALEX instead of behind it.
    """
    allow_foreground_for_any_process()

    # Method 1: os.startfile (Windows only, most reliable from background threads)
    if hasattr(os, "startfile"):
        try:
            os.startfile(url)
            log.info(f"🌐 Opened URL (os.startfile): {url}")
            return True
        except Exception as e:
            log.debug(f"os.startfile failed: {e}")

    # Method 2: cmd's start. The empty "" is the window-title argument — without
    # it, start treats a quoted URL as the title and opens nothing.
    try:
        subprocess.Popen(["cmd", "/c", "start", "", url], shell=False)
        log.info(f"🌐 Opened URL (cmd start): {url}")
        return True
    except Exception as e:
        log.debug(f"cmd start failed: {e}")

    # Method 3: webbrowser (may silently fail from threads)
    try:
        if webbrowser.open(url):
            log.info(f"🌐 Opened URL (webbrowser): {url}")
            return True
        log.error(f"webbrowser.open returned False for {url}")
        return False
    except Exception as e:
        log.error(f"All browser methods failed for {url}: {e}")
        return False


# Backwards-compatible alias for the previous private name
_open_url = open_url


def _page_hint(url: str) -> str:
    """A title fragment to look for when raising the browser, from the host."""
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return ""
    host = host.removeprefix("www.")
    known = {
        "youtube.com": "YouTube",
        "youtu.be": "YouTube",
        "google.com": "Google",
        "github.com": "GitHub",
        "duckduckgo.com": "DuckDuckGo",
    }
    if host in known:
        return known[host]
    return host.split(".")[0].title() if host else ""


@tool(
    name="web_search",
    description="Search the web using DuckDuckGo and return summarized results with snippets",
    parameters={
        "query": {"type": "string", "description": "Search query", "required": True},
        "num_results": {"type": "integer", "description": "Number of results to return (default 5)", "required": False},
    },
    category="web",
    examples=["web_search({'query': 'Python asyncio tutorial', 'num_results': 3})"],
)
def web_search(params: dict) -> ToolResult:
    query = params.get("query", "")
    num_results = int(params.get("num_results", 5))

    if not query:
        return ToolResult(success=False, error="No search query provided")

    try:
        # DuckDuckGo Instant Answer API (no API key required)
        url = f"https://api.duckduckgo.com/?q={quote_plus(query)}&format=json&no_redirect=1&no_html=1"
        resp = requests.get(url, timeout=10)
        data = resp.json()

        results = []

        # Abstract (main answer)
        if data.get("AbstractText"):
            results.append({
                "title": data.get("Heading", "Summary"),
                "snippet": data["AbstractText"],
                "url": data.get("AbstractURL", ""),
                "type": "abstract",
            })

        # Related topics
        for topic in data.get("RelatedTopics", [])[:num_results - len(results)]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append({
                    "title": topic.get("Text", "")[:80],
                    "snippet": topic.get("Text", ""),
                    "url": topic.get("FirstURL", ""),
                    "type": "related",
                })

        if not results:
            # Open browser as fallback
            open_url(f"https://duckduckgo.com/?q={quote_plus(query)}")
            focus_browser("DuckDuckGo")
            return ToolResult(
                success=True,
                message=f"Opened DuckDuckGo search for: {query}",
                data={"query": query, "results": []},
            )

        # Format for LLM
        summary_lines = [f"Search results for '{query}':"]
        for i, r in enumerate(results[:num_results], 1):
            summary_lines.append(f"{i}. {r['title']}: {r['snippet'][:200]}")
            if r["url"]:
                summary_lines.append(f"   URL: {r['url']}")

        message = "\n".join(summary_lines)
        log.info(f"🔍 Web search '{query}': {len(results)} results")

        return ToolResult(
            success=True,
            message=message,
            data={"query": query, "results": results},
        )

    except Exception as e:
        log.error(f"Web search failed: {e}")
        # Fallback to browser
        try:
            open_url(f"https://duckduckgo.com/?q={quote_plus(query)}")
            focus_browser("DuckDuckGo")
            return ToolResult(
                success=True,
                message=f"Opened search in browser for: {query}",
                data={"query": query, "results": []},
            )
        except Exception:
            return ToolResult(success=False, error=str(e))


@tool(
    name="web_open",
    description=(
        "Open a web page in the browser. Use for opening a site by name or URL. "
        "To play or search a video, prefer youtube_play or youtube_search."
    ),
    parameters={
        "url": {"type": "string", "description": "The URL to open", "required": True},
        "focus": {"type": "boolean", "description": "Bring the browser to the front (default true)", "required": False},
    },
    category="web",
    examples=["web_open({'url': 'https://github.com'})"],
)
def web_open(params: dict) -> ToolResult:
    url = params.get("url", "")
    if not url:
        return ToolResult(success=False, error="No URL provided")

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        if not open_url(url):
            return ToolResult(success=False, error=f"Couldn't open {url} in a browser")

        # Focus by default. The LLM never remembered to ask for it, which is
        # why tabs kept opening behind the ALEX window.
        if params.get("focus", True):
            focus_browser(_page_hint(url))

        return ToolResult(success=True, message=f"Opened {url} in your browser")
    except Exception as e:
        return ToolResult(success=False, error=str(e))


@tool(
    name="web_scrape",
    description="Fetch and extract text content from a web page URL",
    parameters={
        "url": {"type": "string", "description": "URL of the page to scrape", "required": True},
        "extract": {"type": "string", "description": "What to extract: 'text' (default), 'links', 'headings'", "required": False},
    },
    category="web",
)
def web_scrape(params: dict) -> ToolResult:
    url = params.get("url", "")
    extract = params.get("extract", "text")

    if not url:
        return ToolResult(success=False, error="No URL provided")

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        resp = requests.get(url, timeout=15, headers=headers)
        resp.raise_for_status()

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")

            # Remove scripts and styles
            for tag in soup(["script", "style", "nav", "footer"]):
                tag.decompose()

            if extract == "links":
                links = [{"text": a.get_text(strip=True), "href": a.get("href", "")}
                         for a in soup.find_all("a", href=True)][:30]
                return ToolResult(success=True, data=links, message=f"Found {len(links)} links")

            elif extract == "headings":
                headings = [{"level": tag.name, "text": tag.get_text(strip=True)}
                            for tag in soup.find_all(["h1", "h2", "h3", "h4"])]
                return ToolResult(success=True, data=headings, message="\n".join(f"{h['level']}: {h['text']}" for h in headings))

            else:  # text
                text = soup.get_text(separator="\n", strip=True)
                # Trim to 3000 chars
                text = text[:3000]
                return ToolResult(success=True, message=text, data={"url": url, "text": text})

        except ImportError:
            # No BeautifulSoup — return raw text
            text = resp.text[:2000]
            return ToolResult(success=True, message=text, data={"url": url, "text": text})

    except Exception as e:
        return ToolResult(success=False, error=f"Failed to fetch {url}: {e}")

