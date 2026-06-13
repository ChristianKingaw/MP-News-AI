import asyncio
import logging
from datetime import datetime, timezone
from app.tasks.celery_app import celery_app
from app.services.phivolcs import phivolcs_service
from app.services.news_api import news_api_service
from app.services.weather_service import weather_service

logger = logging.getLogger(__name__)

_LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(_LOOP)

def _run_async(coro):
    return _LOOP.run_until_complete(coro)


async def _poll_and_store():
    from app.database import async_session_factory
    from app.services.alert_service import filter_and_store_article
    from app.models.task_log import TaskLog, TaskStatus
    from app.models.news import NewsArticle
    from sqlalchemy import select, func

    async with async_session_factory() as db:
        started_at = datetime.now(timezone.utc)
        task_log = TaskLog(
            task_name="poll_external_sources",
            status=TaskStatus.STARTED,
            started_at=started_at,
        )
        db.add(task_log)

        try:
            phivolcs_data = await phivolcs_service.fetch_earthquake_data()
            logger.info("Fetched %d PHIVOLCS earthquake records", len(phivolcs_data))

            for article in phivolcs_data:
                await filter_and_store_article(db, article)

            news_data = await news_api_service.fetch_from_news_api()
            logger.info("Fetched %d News API articles", len(news_data))

            for article in news_data:
                await filter_and_store_article(db, article)

            rss_data = await news_api_service.fetch_from_rss_feeds()
            logger.info("Fetched %d RSS feed articles", len(rss_data))

            for article in rss_data:
                await filter_and_store_article(db, article)

            newsdata_data = await news_api_service.fetch_from_newsdata()
            logger.info("Fetched %d NewsData articles", len(newsdata_data))

            for article in newsdata_data:
                await filter_and_store_article(db, article)

            weather_alerts = await weather_service.fetch_weather_alerts()
            logger.info("Fetched %d weather alerts", len(weather_alerts))

            for article in weather_alerts:
                await filter_and_store_article(db, article)

            task_log.status = TaskStatus.SUCCESS
            task_log.finished_at = datetime.now(timezone.utc)
            task_log.items_processed = len(phivolcs_data) + len(news_data) + len(rss_data) + len(newsdata_data) + len(weather_alerts)

            await db.commit()
            logger.info("Poll cycle completed successfully")

        except Exception as e:
            logger.exception("Poll cycle failed: %s", e)
            task_log.status = TaskStatus.FAILED
            task_log.finished_at = datetime.now(timezone.utc)
            task_log.error_message = str(e)
            db.add(task_log)
            await db.commit()


async def _process_pending():
    from app.database import async_session_factory
    from app.services.alert_service import process_pending_articles
    from app.models.task_log import TaskLog, TaskStatus

    async with async_session_factory() as db:
        started_at = datetime.now(timezone.utc)
        task_log = TaskLog(
            task_name="process_pending_articles",
            status=TaskStatus.STARTED,
            started_at=started_at,
        )
        db.add(task_log)

        try:
            posts = await process_pending_articles(db)
            logger.info("Processed & published %d pending articles", len(posts))

            task_log.status = TaskStatus.SUCCESS
            task_log.finished_at = datetime.now(timezone.utc)
            task_log.items_processed = len(posts)

            await db.commit()
        except Exception as e:
            logger.exception("Process pending articles failed: %s", e)
            task_log.status = TaskStatus.FAILED
            task_log.finished_at = datetime.now(timezone.utc)
            task_log.error_message = str(e)
            db.add(task_log)
            await db.commit()


async def _retry_failed():
    from app.database import async_session_factory
    from app.services.alert_service import retry_failed_posts

    async with async_session_factory() as db:
        try:
            retried = await retry_failed_posts(db)
            logger.info("Retried %d failed posts", len(retried))
            await db.commit()
        except Exception as e:
            logger.exception("Retry failed posts failed: %s", e)
            await db.rollback()


@celery_app.task(name="app.tasks.scheduler.poll_external_sources")
def poll_external_sources():
    _run_async(_poll_and_store())


@celery_app.task(name="app.tasks.scheduler.process_pending_articles")
def process_pending_articles():
    _run_async(_process_pending())


@celery_app.task(name="app.tasks.scheduler.publish_approved_posts")
def publish_approved_posts():
    from app.database import async_session_factory
    from app.services.alert_service import auto_publish_approved_posts

    async def _publish():
        async with async_session_factory() as db:
            try:
                published = await auto_publish_approved_posts(db)
                logger.info("Published %d approved posts", len(published))
                await db.commit()
            except Exception as e:
                logger.exception("Publish cycle failed: %s", e)
                await db.rollback()

    _run_async(_publish())


@celery_app.task(name="app.tasks.scheduler.retry_failed_posts")
def retry_failed_posts_task():
    _run_async(_retry_failed())


@celery_app.task(name="app.tasks.scheduler.process_article")
def process_article_task(article_id: str):
    from app.database import async_session_factory
    from app.services.alert_service import process_article_workflow
    from app.services.facebook_service import facebook_service

    async def _process():
        async with async_session_factory() as db:
            try:
                post = await process_article_workflow(db, article_id)
                if post:
                    logger.info("Processed article %s -> post %s", article_id, post.id)
                    publish_result = await facebook_service.publish_post(
                        post.caption, post.image_path
                    )
                    if publish_result["error"]:
                        post.retry_count = 1
                        post.last_error = publish_result["error"]
                        logger.warning("Publish failed for post %s: %s", post.id, publish_result["error"])
                    else:
                        post.status = post.status.__class__.PUBLISHED
                        post.fb_post_id = publish_result["fb_post_id"]
                        post.fb_post_url = publish_result["fb_post_url"]
                        post.published_at = datetime.now(timezone.utc)
                        logger.info("Published post %s -> FB %s", post.id, post.fb_post_id)
                    db.add(post)
                await db.commit()
            except Exception as e:
                logger.exception("Article processing failed: %s", e)
                await db.rollback()

    _run_async(_process())