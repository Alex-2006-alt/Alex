"""
ALEX — Web Tools
Web search, URL opening, and page scraping capabilities.
"""

import webbrowser
from urllib.parse import quote_plus

import requests

from core.tool_registry import tool, ToolResult, SafetyLevel
from utils.logger import log
from utils.window_utils import focus_window


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
            webbrowser.open(f"https://duckduckgo.com/?q={quote_plus(query)}")
            focus_window("DuckDuckGo", timeout=3.0)
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
            webbrowser.open(f"https://duckduckgo.com/?q={quote_plus(query)}")
            focus_window("DuckDuckGo", timeout=3.0)
            return ToolResult(
                success=True,
                message=f"Opened search in browser for: {query}",
                data={"query": query, "results": []},
            )
        except Exception:
            return ToolResult(success=False, error=str(e))


@tool(
    name="web_open",
    description="Open a URL in the default web browser",
    parameters={
        "url": {"type": "string", "description": "The URL to open", "required": True},
        "focus_title": {"type": "string", "description": "Optional title substring to bring the browser to front (e.g., 'YouTube')", "required": False},
    },
    category="web",
)
def web_open(params: dict) -> ToolResult:
    url = params.get("url", "")
    if not url:
        return ToolResult(success=False, error="No URL provided")

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        webbrowser.open(url)
        log.info(f"🌐 Opened URL: {url}")
        
        focus_title = params.get("focus_title")
        if focus_title:
            focus_window(focus_title, timeout=3.0)
            
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

@tool(
    name="youtube_play",
    description="Search and play a video on YouTube",
    parameters={
        "query": {"type": "string", "description": "The search query for the YouTube video", "required": True},
    },
    category="web",
)
def youtube_play(params: dict) -> ToolResult:
    import re
    query = params.get("query", "")
    if not query:
        return ToolResult(success=False, error="No search query provided")

    search_url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        resp = requests.get(search_url, timeout=10, headers=headers)
        resp.raise_for_status()
        
        # Look for the first video ID
        match = re.search(r'href="/watch\?v=([^"]+)"', resp.text)
        if match:
            video_id = match.group(1).split("&")[0]  # strip extra query params
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            
            webbrowser.open(video_url)
            focus_window("YouTube", timeout=3.0)
            
            log.info(f"▶️ Playing YouTube video: {video_url}")
            return ToolResult(success=True, message=f"Playing '{query}' on YouTube...")
            
    except Exception as e:
        log.warning(f"Failed to scrape YouTube for '{query}': {e}")
        
    # Fallback to search results page
    webbrowser.open(search_url)
    focus_window("YouTube", timeout=3.0)
    return ToolResult(success=True, message=f"Opened YouTube search for '{query}'")

