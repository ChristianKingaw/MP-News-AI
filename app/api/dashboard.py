from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.news import NewsArticle, ArticleStatus
from app.models.post import FacebookPost, PostStatus
from app.models.alert import DisasterAlert, AlertStatus

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=dict)
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)):
    total_articles = (
        await db.execute(select(func.count(NewsArticle.id)))
    ).scalar() or 0

    disaster_articles = (
        await db.execute(
            select(func.count(NewsArticle.id)).where(
                NewsArticle.is_disaster_related == True
            )
        )
    ).scalar() or 0

    pending_posts = (
        await db.execute(
            select(func.count(FacebookPost.id)).where(
                FacebookPost.status == PostStatus.PENDING_REVIEW
            )
        )
    ).scalar() or 0

    approved_posts = (
        await db.execute(
            select(func.count(FacebookPost.id)).where(
                FacebookPost.status == PostStatus.APPROVED
            )
        )
    ).scalar() or 0

    published_posts = (
        await db.execute(
            select(func.count(FacebookPost.id)).where(
                FacebookPost.status == PostStatus.PUBLISHED
            )
        )
    ).scalar() or 0

    failed_posts = (
        await db.execute(
            select(func.count(FacebookPost.id)).where(
                FacebookPost.status == PostStatus.FAILED
            )
        )
    ).scalar() or 0

    active_alerts = (
        await db.execute(
            select(func.count(DisasterAlert.id)).where(
                DisasterAlert.status == AlertStatus.ACTIVE
            )
        )
    ).scalar() or 0

    return {
        "total_articles": total_articles,
        "disaster_related_articles": disaster_articles,
        "pending_review_posts": pending_posts,
        "approved_posts": approved_posts,
        "published_posts": published_posts,
        "failed_posts": failed_posts,
        "active_alerts": active_alerts,
    }


@router.get("/recent-activity", response_model=dict)
async def get_recent_activity(db: AsyncSession = Depends(get_db)):
    recent_articles = (
        await db.execute(
            select(NewsArticle)
            .order_by(NewsArticle.created_at.desc())
            .limit(5)
        )
    )
    articles = recent_articles.scalars().all()

    recent_posts = (
        await db.execute(
            select(FacebookPost)
            .order_by(FacebookPost.created_at.desc())
            .limit(5)
        )
    )
    posts = recent_posts.scalars().all()

    return {
        "recent_articles": [
            {
                "id": str(a.id),
                "title": a.title,
                "status": a.status.value,
                "created_at": a.created_at.isoformat(),
            }
            for a in articles
        ],
        "recent_posts": [
            {
                "id": str(p.id),
                "caption": p.caption[:200] if p.caption else "",
                "status": p.status.value,
                "created_at": p.created_at.isoformat(),
            }
            for p in posts
        ],
    }