import logging
import httpx
import feedparser
from datetime import datetime, timezone
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
        self.newsdata_key = settings.NEWSDATA_API_KEY
        self.keywords = settings.disaster_keywords_list

    @staticmethod
    def _parse_date(date_str: str | None) -> datetime | None:
        if not date_str:
            return None
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return dt.astimezone(timezone.utc)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_rss_date(entry) -> datetime | None:
        published_parsed = entry.get("published_parsed")
        if published_parsed:
            try:
                from time import mktime
                ts = mktime(published_parsed)
                return datetime.fromtimestamp(ts, tz=timezone.utc)
            except Exception:
                pass
        published = entry.get("published", "")
        if published:
            try:
                from email.utils import parsedate_to_datetime
                return parsedate_to_datetime(published).astimezone(timezone.utc)
            except Exception:
                pass
        return None

    async def fetch_from_newsdata(self) -> list[dict]:
        results: list[dict] = []

        if not self.newsdata_key or self.newsdata_key == "your-newsdata-api-key":
            logger.info("No NewsData API key configured. Skipping NewsData fetch.")
            return results

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    "https://newsdata.io/api/1/latest",
                    params={
                        "apikey": self.newsdata_key,
                        "country": "ph",
                        "language": "tl,en",
                        "category": settings.NEWSDATA_CATEGORIES,
                    },
                )
                response.raise_for_status()
                data = response.json()

                for article in data.get("results", []):
                    title = article.get("title", "")
                    description = article.get("description", "")
                    content = article.get("content", description or "")
                    url = article.get("link", "")

                    if self.is_disaster_related(f"{title} {description}"):
                        image_url = article.get("image_url") or article.get("urlToImage")
                        results.append({
                            "source_type": "news_api",
                            "source_url": url,
                            "source_image_url": image_url,
                            "title": title,
                            "content": content or description,
                            "keywords_matched": self.get_matched_keywords(
                                f"{title} {description}"
                            ),
                            "is_disaster_related": True,
                            "source_published_at": self._parse_date(article.get("pubDate")),
                        })

        except httpx.HTTPError as e:
            logger.error("NewsData API request failed: %s", e)
        except Exception as e:
            logger.exception("NewsData API service error: %s", e)

        return results

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
                        image_url = (
                            article.get("urlToImage")
                        )
                        results.append({
                            "source_type": "news_api",
                            "source_url": url,
                            "source_image_url": image_url,
                            "title": title,
                            "content": content or description,
                            "keywords_matched": self.get_matched_keywords(
                                f"{title} {description}"
                            ),
                            "is_disaster_related": True,
                            "source_published_at": self._parse_date(article.get("publishedAt")),
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
                        content_html = ""
                        content_list = entry.get("content", [])
                        if content_list:
                            content_html = content_list[0].get("value", "") or ""

                        image_url = self._extract_rss_image(entry, summary_text, content_html)
                        results.append({
                            "source_type": "rss_feed",
                            "source_url": link,
                            "source_image_url": image_url,
                            "title": title,
                            "content": summary_clean or title,
                            "keywords_matched": self.get_matched_keywords(combined_text),
                            "is_disaster_related": True,
                            "source_published_at": self._parse_rss_date(entry),
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

    def _extract_rss_image(self, entry, summary_html: str = "", content_html: str = "") -> str | None:
        media_content = entry.get("media_content", [])
        for media in media_content:
            if media.get("type", "").startswith("image/") or media.get("medium") == "image":
                return media.get("url")

        media_thumbnail = entry.get("media_thumbnail", [])
        for thumb in media_thumbnail:
            return thumb.get("url")

        links = entry.get("links", [])
        for link in links:
            if link.get("type", "").startswith("image/"):
                return link.get("href")

        enclosures = entry.get("enclosures", [])
        for enc in enclosures:
            if enc.get("type", "").startswith("image/"):
                return enc.get("href")

        for html_source in (summary_html, content_html):
            if html_source:
                try:
                    soup = BeautifulSoup(html_source, "lxml")
                    img = soup.find("img")
                    if img and img.get("src"):
                        return img["src"]
                except Exception:
                    pass

        return None


news_api_service = NewsAPIService()