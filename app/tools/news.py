import re
import requests, feedparser
from app.config import NEWSDATA_API_KEY, to_yf_symbol

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """Remove HTML tags and collapse whitespace from RSS summaries."""
    return re.sub(r"\s+", " ", _TAG_RE.sub("", text or "")).strip()

def get_news_items(ticker: str, company: str = "") -> list[dict]:
    """Collect recent headlines as structured items for the dashboard.

    Each item: {title, summary, source, url, published}. URLs are preserved so
    the frontend can render clickable links.
    """
    items: list[dict] = []
    seen_titles = set()
    query = company or ticker

    def _add(title, summary, source, url, published):
        title = _strip_html(title)
        if not title:
            return
        key = title.lower()
        if key in seen_titles:
            return
        seen_titles.add(key)
        items.append({
            "title": title,
            "summary": _strip_html(summary)[:240],
            "source": _strip_html(source),
            "url": (url or "").strip(),
            "published": _strip_html(published),
        })

    # 1) NewsData.io — Indian business news (200 credits/day, no card)
    try:
        r = requests.get("https://newsdata.io/api/1/news", params={
            "apikey": NEWSDATA_API_KEY,
            "q": query,
            "country": "in",
            "category": "business",
            "language": "en",
        }, timeout=10)
        for a in r.json().get("results", [])[:15]:
            _add(a.get("title", ""), a.get("description", "") or "",
                 a.get("source_id", "") or "NewsData",
                 a.get("link", ""), a.get("pubDate", ""))
    except Exception:
        pass

    # 2) Google News RSS — unlimited, no key. Entries carry link + source + date.
    try:
        feed = feedparser.parse(
            f"https://news.google.com/rss/search?q={query}+stock+NSE&hl=en-IN&gl=IN&ceid=IN:en")
        for e in feed.entries[:15]:
            src = ""
            if e.get("source"):
                src = e.source.get("title", "") if hasattr(e.source, "get") else str(e.source)
            _add(e.get("title", ""), e.get("summary", ""), src or "Google News",
                 e.get("link", ""), e.get("published", ""))
    except Exception:
        pass

    return items


def get_news(ticker: str, company: str = "") -> list[str]:
    """Plain-string headlines (title + summary) for the sentiment LLM / RAG."""
    out = []
    for it in get_news_items(ticker, company):
        text = it["title"]
        if it["summary"]:
            text += ". " + it["summary"]
        out.append(text)
    return out
    