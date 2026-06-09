import asyncio
import logging
from app.tasks.celery_app import celery_app
from app.services.phivolcs import phivolcs_service
from app.services.news_api import news_api_service

logger = logging.getLogger(__name__)


async def _poll_and_store():
    from app.database import async_session_factory
    from app.services.alert_service import filter_and_store_article

    async with async_session_factory() as db:
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

            await db.commit()
            logger.info("Poll cycle completed successfully")

        except Exception as e:
            logger.exception("Poll cycle failed: %s", e)
            await db.rollback()


@celery_app.task(name="app.tasks.scheduler.poll_external_sources")
def poll_external_sources():
    asyncio.run(_poll_and_store())


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

    asyncio.run(_publish())


@celery_app.task(name="app.tasks.scheduler.process_article")
def process_article_task(article_id: str):
    from app.database import async_session_factory
    from app.services.alert_service import process_article_workflow

    async def _process():
        async with async_session_factory() as db:
            try:
                post = await process_article_workflow(db, article_id)
                if post:
                    logger.info("Processed article %s -> post %s", article_id, post.id)
                await db.commit()
            except Exception as e:
                logger.exception("Article processing failed: %s", e)
                await db.rollback()

    asyncio.run(_process())