import requests, feedparser
from app.config import NEWSDATA_API_KEY, to_yf_symbol

def get_news(ticker: str, company: str = "") -> list[str]:
    """Collect recent Indian-market headlines from NewsData.io + RSS (free)."""
    items = []
    query = company or ticker

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
            items.append(f"{a.get('title','')}. {a.get('description','') or ''}")
    except Exception:
        pass
    # 2) Google News RSS for the Indian ticker - unlimited, no key
    feed = feedparser.parse(
        f"https://news.google.com/rss/search?q={query}+stock+NSE&hl=en-IN&gl=IN&ceid=IN:en")
    for e in feed.entries[:15]:
        items.append(f"{e.get('title','')}. {e.get('summary','')}")
    return [i for i in items if i.strip()]
    