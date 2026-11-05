"""Web search and browser interaction tools."""

import webbrowser

import httpx

from tools.registry import register_tool


@register_tool(
    name="search_web",
    description="Searches the web for current information, news, or technical documentation using DuckDuckGo."
)
async def search_web(query: str) -> str:
    """Performs instant web search via DuckDuckGo API."""
    url = "https://api.duckduckgo.com/"
    params = {
        "q": query,
        "format": "json",
        "no_redirect": "1",
        "no_html": "1",
        "skip_disambig": "1"
    }

    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(url, params=params)
            data = resp.json()

            abstract = data.get("AbstractText")
            if abstract:
                return f"Search result for '{query}': {abstract}"

            related = data.get("RelatedTopics", [])
            snippets = []
            for item in related[:3]:
                if isinstance(item, dict) and "Text" in item:
                    snippets.append(item["Text"])

            if snippets:
                return f"Search findings for '{query}': " + " | ".join(snippets)

            # Fallback: open search in default browser
            webbrowser.open(f"https://www.google.com/search?q={query}")
            return f"Opened Google search results for '{query}' in your browser, sir."
    except Exception as e:
        webbrowser.open(f"https://www.google.com/search?q={query}")
        return f"Opened query in browser ({e})."


@register_tool(
    name="open_url",
    description="Opens any web URL in the user's default web browser."
)
def open_url(url: str) -> str:
    """Opens a website in the default browser."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    webbrowser.open(url)
    return f"Opened {url} in your browser, sir."
