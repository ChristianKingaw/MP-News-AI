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

    article = NewsArticle(
        source_type=SourceType(article_data.get("source_type", "news_api")),
        source_url=article_data.get("source_url"),
        title=title,
        content=content,
        content_hash=content_hash,
        keywords_matched=article_data.get("keywords_matched"),
        is_disaster_related=article_data.get("is_disaster_related", True),
        status=ArticleStatus.FILTERED,
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
    result = await db.execute(
        select(NewsArticle).where(NewsArticle.id == article_id)
    )
    article = result.scalar_one_or_none()
    if not article:
        return None

    summary = await openai_service.summarize_article(
        article.title, article.content
    )
    if summary:
        article.summary = summary
        article.status = ArticleStatus.SUMMARIZED
        article.processed_at = datetime.utcnow()

    caption = await openai_service.generate_caption(
        article.title, summary or article.content
    )

    image_prompt = await openai_service.generate_image_prompt(caption)
    image_url, image_path = await openai_service.generate_image(
        image_prompt or caption
    )

    post = FacebookPost(
        article_id=article.id,
        caption=caption,
        summary=summary or article.content[:500],
        image_prompt=image_prompt,
        image_url=image_url,
        image_path=image_path,
        status=PostStatus.PENDING_REVIEW,
    )
    db.add(post)
    article.status = ArticleStatus.SUMMARIZED
    db.add(article)

    return post


async def process_pending_articles(db: AsyncSession) -> list[FacebookPost]:
    result = await db.execute(
        select(NewsArticle)
        .where(
            NewsArticle.status == ArticleStatus.FILTERED,
            NewsArticle.is_disaster_related == True,
        )
        .limit(10)
    )
    articles = result.scalars().all()

    posts = []
    for article in articles:
        classified = await classify_article(db, article.id)
        if classified and classified.is_disaster_related:
            if classified.location_relevance_score and classified.location_relevance_score >= 0.2:
                post = await process_article_workflow(db, classified.id)
                if post:
                    posts.append(post)

    return posts


async def auto_publish_approved_posts(db: AsyncSession) -> list[FacebookPost]:
    from app.services.facebook_service import facebook_service

    result = await db.execute(
        select(FacebookPost).where(FacebookPost.status == PostStatus.APPROVED)
        .order_by(FacebookPost.created_at)
        .limit(5)
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
        .limit(10)
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