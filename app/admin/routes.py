import logging
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.news import NewsArticle, ArticleStatus
from app.models.post import FacebookPost, PostStatus
from app.models.alert import DisasterAlert, AlertStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin-dashboard"])

templates = Jinja2Templates(directory="app/admin/templates")


@router.get("", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    total_articles = (
        await db.execute(select(func.count(NewsArticle.id)))
    ).scalar() or 0
    total_posts = (
        await db.execute(select(func.count(FacebookPost.id)))
    ).scalar() or 0
    active_alerts = (
        await db.execute(
            select(func.count(DisasterAlert.id)).where(
                DisasterAlert.status == AlertStatus.ACTIVE
            )
        )
    ).scalar() or 0
    pending_review = (
        await db.execute(
            select(func.count(FacebookPost.id)).where(
                FacebookPost.status == PostStatus.PENDING_REVIEW
            )
        )
    ).scalar() or 0
    published = (
        await db.execute(
            select(func.count(FacebookPost.id)).where(
                FacebookPost.status == PostStatus.PUBLISHED
            )
        )
    ).scalar() or 0

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "total_articles": total_articles,
            "total_posts": total_posts,
            "active_alerts": active_alerts,
            "pending_review": pending_review,
            "published": published,
        },
    )


@router.get("/posts", response_class=HTMLResponse)
async def admin_posts(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(FacebookPost).order_by(FacebookPost.created_at.desc()).limit(50)
    )
    posts = result.scalars().all()

    return templates.TemplateResponse(
        "posts.html",
        {
            "request": request,
            "posts": posts,
        },
    )


@router.get("/news", response_class=HTMLResponse)
async def admin_news(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(NewsArticle)
        .order_by(NewsArticle.created_at.desc())
        .limit(50)
    )
    articles = result.scalars().all()

    return templates.TemplateResponse(
        "news.html",
        {
            "request": request,
            "articles": articles,
        },
    )


@router.get("/alerts", response_class=HTMLResponse)
async def admin_alerts(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(DisasterAlert)
        .order_by(DisasterAlert.reported_at.desc())
        .limit(50)
    )
    alerts = result.scalars().all()

    return templates.TemplateResponse(
        "alerts.html",
        {
            "request": request,
            "alerts": alerts,
        },
    )