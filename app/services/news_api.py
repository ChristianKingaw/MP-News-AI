import logging
import httpx
import feedparser
from bs4 import BeautifulSoup
from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


RSS_FEEDS = [
    "https://www.philstar.com/rss/headlines",
    "https://newsinfo.inquirer.net/feed",
    "https://www.rappler.com/feed/",
]


class NewsAPIService:
    def __init__(self):
        self.api_key = settings.NEWS_API_KEY
        self.keywords = settings.disaster_keywords_list

    async def fetch_from_news_api(self) -> list[dict]:
        results: list[dict] = []

        if not self.api_key or self.api_key == "your-news-api-key":
            logger.info("No News API key configured. Skipping News API fetch.")
            return results

        try:
            query = " OR ".join(settings.disaster_keywords_list[:6])
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    "https://newsapi.org/v2/everything",
                    params={
                        "q": query,
                        "language": "tl",
                        "sortBy": "publishedAt",
                        "pageSize": 10,
                        "apiKey": self.api_key,
                    },
                )
                response.raise_for_status()
                data = response.json()

                for article in data.get("articles", []):
                    title = article.get("title", "")
                    description = article.get("description", "")
                    content = article.get("content", description or "")
                    url = article.get("url", "")

                    if self.is_disaster_related(f"{title} {description}"):
                        results.append({
                            "source_type": "news_api",
                            "source_url": url,
                            "title": title,
                            "content": content or description,
                            "keywords_matched": self.get_matched_keywords(
                                f"{title} {description}"
                            ),
                            "is_disaster_related": True,
                        })

        except httpx.HTTPError as e:
            logger.error("News API request failed: %s", e)
        except Exception as e:
            logger.exception("News API service error: %s", e)

        return results

    async def fetch_from_rss_feeds(self) -> list[dict]:
        results: list[dict] = []

        for feed_url in RSS_FEEDS:
            try:
                feed = feedparser.parse(feed_url)

                if not feed.entries:
                    logger.warning("RSS feed returned no entries: %s", feed_url)

                for entry in feed.entries[:5]:
                    title = entry.get("title", "")
                    summary_text = entry.get("summary", "")
                    summary_clean = BeautifulSoup(summary_text, "lxml").get_text()
                    link = entry.get("link", "")

                    combined_text = f"{title} {summary_clean}"

                    if self.is_disaster_related(combined_text):
                        results.append({
                            "source_type": "rss_feed",
                            "source_url": link,
                            "title": title,
                            "content": summary_clean or title,
                            "keywords_matched": self.get_matched_keywords(combined_text),
                            "is_disaster_related": True,
                        })

            except Exception as e:
                logger.error("RSS feed %s failed: %s", feed_url, e)

        return results

    def is_disaster_related(self, text: str) -> bool:
        text_lower = text.lower()
        return any(kw in text_lower for kw in self.keywords)

    def get_matched_keywords(self, text: str) -> str:
        text_lower = text.lower()
        matched = [kw for kw in self.keywords if kw in text_lower]
        return ",".join(matched) if matched else ""


news_api_service = NewsAPIService()