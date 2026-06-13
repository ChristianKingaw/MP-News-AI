import logging
import uuid
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.news import NewsArticle, ArticleStatus, SourceType, RiskLevel
from app.models.post import FacebookPost, PostStatus
from app.models.alert import DisasterAlert, AlertStatus
from app.services.openai_service import openai_service
from app.services.ai_service import ai_service

logger = logging.getLogger(__name__)


def _parse_weather_metadata(title: str, content: str) -> dict:
    import re

    meta: dict = {
        "condition": "",
        "temp": 0,
        "is_raining": False,
        "rain_mm": 0,
        "forecast_rain_total": 0,
        "is_extremely_hot": False,
    }

    temp_match = re.search(r"Temperature:\s*([\d.]+)", content)
    if temp_match:
        meta["temp"] = float(temp_match.group(1))
        if meta["temp"] >= 32:
            meta["is_extremely_hot"] = True

    condition_match = re.search(r"Condition:\s*(.+?)(?:\n|$)", content)
    if condition_match:
        meta["condition"] = condition_match.group(1).strip()

    rain_match = re.search(r"Rainfall\s*\([^)]+\):\s*([\d.]+)", content)
    if rain_match:
        meta["rain_mm"] = float(rain_match.group(1))
        if meta["rain_mm"] > 0:
            meta["is_raining"] = True

    forecast_rain_match = re.search(r"Total Expected Rainfall:\s*([\d.]+)", content)
    if forecast_rain_match:
        meta["forecast_rain_total"] = float(forecast_rain_match.group(1))
        if meta["forecast_rain_total"] > 0:
            meta["is_raining"] = True

    if any(w in content.lower() for w in ["rain", "thunderstorm", "drizzle", "shower"]):
        meta["is_raining"] = True

    return meta


async def _capture_or_generate_image(article: NewsArticle, caption: str) -> tuple[str | None, str | None, str | None]:
    if article.source_image_url:
        image_path = await openai_service.download_source_image(article.source_image_url)
        if image_path:
            logger.info("Using source image from article: %s", article.source_image_url)
            return article.source_image_url, image_path, None

    image_prompt = await openai_service.generate_image_prompt(caption)
    image_url, image_path = await openai_service.generate_image(image_prompt or caption)
    return image_url, image_path, image_prompt


async def filter_and_store_article(
    db: AsyncSession, article_data: dict
) -> NewsArticle | None:
    title = article_data.get("title", "")
    content = article_data.get("content", "")

    existing = await db.execute(
        select(NewsArticle).where(
            NewsArticle.title == title,
            NewsArticle.source_url == article_data.get("source_url"),
        )
    )
    if existing.scalar_one_or_none():
        return None

    content_hash = NewsArticle.compute_content_hash(title, content)
    hash_existing = await db.execute(
        select(NewsArticle).where(NewsArticle.content_hash == content_hash)
    )
    if hash_existing.scalar_one_or_none():
        return None

    already_published = await db.execute(
        select(NewsArticle).where(
            NewsArticle.content_hash == content_hash,
            NewsArticle.status.in_([ArticleStatus.SUMMARIZED, ArticleStatus.PUBLISHED]),
        )
    )
    if already_published.scalar_one_or_none():
        logger.info("Skipping duplicate: content already processed (hash=%s)", content_hash[:12])
        return None

    article = NewsArticle(
        source_type=SourceType(article_data.get("source_type", "news_api")),
        source_url=article_data.get("source_url"),
        source_image_url=article_data.get("source_image_url"),
        title=title,
        content=content,
        content_hash=content_hash,
        keywords_matched=article_data.get("keywords_matched"),
        is_disaster_related=article_data.get("is_disaster_related", True),
        status=ArticleStatus.FILTERED,
        source_published_at=article_data.get("source_published_at"),
    )
    db.add(article)
    await db.flush()
    return article


async def classify_article(db: AsyncSession, article_id: uuid.UUID) -> NewsArticle | None:
    result = await db.execute(
        select(NewsArticle).where(NewsArticle.id == article_id)
    )
    article = result.scalar_one_or_none()
    if not article:
        return None

    if article.status in (ArticleStatus.CLASSIFIED, ArticleStatus.SUMMARIZED, ArticleStatus.PUBLISHED):
        return article

    analysis = await ai_service.full_analysis(article.title, article.content)

    article.is_disaster_related = analysis["is_disaster_related"]
    article.status = ArticleStatus.CLASSIFIED

    if analysis["is_disaster_related"]:
        severity_str = analysis["severity"] or "low"
        article.severity = RiskLevel(severity_str)
        article.affected_location = analysis["affected_location"]
        article.location_relevance_score = analysis["location_relevance_score"]

    article.processed_at = datetime.utcnow()
    db.add(article)
    await db.flush()
    return article


async def process_article_workflow(
    db: AsyncSession, article_id: uuid.UUID
) -> FacebookPost | None:
    existing_post = await db.execute(
        select(FacebookPost)
        .where(FacebookPost.article_id == article_id)
        .order_by(FacebookPost.created_at.desc())
        .limit(1)
    )
    post = existing_post.scalar_one_or_none()
    if post:
        return post

    classified = await classify_article(db, article_id)
    if not classified:
        return None

    if classified.content_hash:
        duplicate_posted = await db.execute(
            select(NewsArticle).where(
                NewsArticle.content_hash == classified.content_hash,
                NewsArticle.id != classified.id,
                NewsArticle.status.in_([ArticleStatus.SUMMARIZED, ArticleStatus.PUBLISHED]),
            ).limit(1)
        )
        if duplicate_posted.scalar_one_or_none():
            classified.status = ArticleStatus.REJECTED
            classified.processed_at = datetime.utcnow()
            db.add(classified)
            return None

    if not classified.is_disaster_related:
        if classified.status != ArticleStatus.REJECTED:
            classified.status = ArticleStatus.REJECTED
            classified.processed_at = datetime.utcnow()
            db.add(classified)
        return None

    if (
        classified.source_type == SourceType.PHIVOLCS
        and classified.location_relevance_score is not None
        and classified.location_relevance_score < 1.0
    ):
        return None

    article = classified

    summary = await openai_service.summarize_article(
        article.title, article.content
    )
    if summary:
        article.summary = summary

    alert_type = detect_alert_type(article.title, article.content)

    if article.source_type == SourceType.RSS_FEED:
        body = summary or article.content[:800]
        caption_parts = [article.title]
        caption_parts.append(body)
        if article.source_url:
            caption_parts.append(f"Read more: {article.source_url}")
        caption = "\n\n".join(caption_parts)
        image_url, image_path, image_prompt = await _capture_or_generate_image(article, caption)
    else:
        source_published_str = None
        if article.source_published_at:
            source_published_str = article.source_published_at.strftime("%B %d, %Y at %I:%M %p")

        weather_meta = None
        if article.source_type == SourceType.WEATHER:
            weather_meta = _parse_weather_metadata(article.title, article.content)

        caption = await openai_service.generate_caption(
            article.title, summary or article.content,
            alert_type=alert_type,
            affected_location=article.affected_location,
            source_published_at=source_published_str,
            source_type=article.source_type.value if article.source_type else "",
            weather_metadata=weather_meta,
        )
        image_url, image_path, image_prompt = await _capture_or_generate_image(article, caption)

    post = FacebookPost(
        article_id=article.id,
        caption=caption,
        summary=summary or article.content[:500],
        image_prompt=image_prompt,
        image_url=image_url,
        image_path=image_path,
        status=PostStatus.APPROVED,
    )
    db.add(post)

    article.status = ArticleStatus.SUMMARIZED
    article.processed_at = datetime.utcnow()
    db.add(article)

    return post


async def process_pending_articles(db: AsyncSession) -> list[FacebookPost]:
    from app.services.facebook_service import facebook_service

    result = await db.execute(
        select(NewsArticle)
        .where(
            NewsArticle.status == ArticleStatus.FILTERED,
            NewsArticle.is_disaster_related == True,
        )
        .order_by(NewsArticle.created_at)
    )
    articles = result.scalars().all()

    published = []
    for article in articles:
        post = await process_article_workflow(db, article.id)
        if not post:
            continue

        publish_result = await facebook_service.publish_post(
            post.caption, post.image_path
        )

        if publish_result["error"]:
            post.retry_count = 1
            post.last_error = publish_result["error"]
            post.status = PostStatus.FAILED if post.retry_count >= 3 else PostStatus.APPROVED
        else:
            post.status = PostStatus.PUBLISHED
            post.fb_post_id = publish_result["fb_post_id"]
            post.fb_post_url = publish_result["fb_post_url"]
            post.published_at = datetime.utcnow()
            published.append(post)

        db.add(post)

    return published


async def auto_publish_approved_posts(db: AsyncSession) -> list[FacebookPost]:
    from app.services.facebook_service import facebook_service

    result = await db.execute(
        select(FacebookPost).where(FacebookPost.status == PostStatus.APPROVED)
        .order_by(FacebookPost.created_at)
    )
    posts = result.scalars().all()

    published = []

    for post in posts:
        publish_result = await facebook_service.publish_post(
            post.caption, post.image_path
        )

        if publish_result["error"]:
            post.retry_count += 1
            post.last_error = publish_result["error"]

            if post.retry_count >= 3:
                post.status = PostStatus.FAILED
                post.error_message = publish_result["error"]
            else:
                post.status = PostStatus.APPROVED
        else:
            post.status = PostStatus.PUBLISHED
            post.fb_post_id = publish_result["fb_post_id"]
            post.fb_post_url = publish_result["fb_post_url"]
            post.published_at = datetime.utcnow()
            published.append(post)

        db.add(post)

    return published


async def retry_failed_posts(db: AsyncSession) -> list[FacebookPost]:
    from app.services.facebook_service import facebook_service

    result = await db.execute(
        select(FacebookPost)
        .where(
            FacebookPost.status == PostStatus.FAILED,
            FacebookPost.retry_count < 3,
        )
    )
    posts = result.scalars().all()

    retried = []
    for post in posts:
        publish_result = await facebook_service.publish_post(
            post.caption, post.image_path
        )

        if publish_result["error"]:
            post.retry_count += 1
            post.last_error = publish_result["error"]
        else:
            post.status = PostStatus.PUBLISHED
            post.fb_post_id = publish_result["fb_post_id"]
            post.fb_post_url = publish_result["fb_post_url"]
            post.published_at = datetime.utcnow()
            retried.append(post)

        db.add(post)

    return retried


def detect_alert_type(title: str, content: str) -> str:
    combined = f"{title} {content}".lower()
    if any(kw in combined for kw in ["earthquake", "lindol", "tremor"]):
        return "earthquake"
    if any(kw in combined for kw in ["flood", "baha"]):
        return "flood"
    if any(kw in combined for kw in ["typhoon", "storm", "bagyo"]):
        return "typhoon"
    if any(kw in combined for kw in ["landslide"]):
        return "landslide"
    if any(kw in combined for kw in ["volcano", "bulkan"]):
        return "volcano"
    if any(kw in combined for kw in ["tsunami"]):
        return "tsunami"
    return "other"