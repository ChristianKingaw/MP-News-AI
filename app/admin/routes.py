import logging
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.news import NewsArticle
from app.models.post import FacebookPost, PostStatus
from app.models.alert import DisasterAlert, AlertStatus
from app.models.audit import AuditLog
from app.models.task_log import TaskLog
from app.models.user import User
from app.api.auth import require_admin_auth, _decode_admin_cookie, AdminAuthRequired

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin-dashboard"])

templates = Jinja2Templates(directory="app/admin/templates")


@router.get("/login", response_class=HTMLResponse)
async def admin_login_page(request: Request, db: AsyncSession = Depends(get_db)):
    username = _decode_admin_cookie(request)
    if username:
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        if user and user.is_active:
            return RedirectResponse(url="/admin", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request})


@router.get("", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_auth),
):
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
    failed_count = (
        await db.execute(
            select(func.count(FacebookPost.id)).where(
                FacebookPost.status == PostStatus.FAILED
            )
        )
    ).scalar() or 0

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": current_user,
            "total_articles": total_articles,
            "total_posts": total_posts,
            "active_alerts": active_alerts,
            "pending_review": pending_review,
            "published": published,
            "failed_count": failed_count,
        },
    )


@router.get("/posts", response_class=HTMLResponse)
async def admin_posts(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_auth),
):
    result = await db.execute(
        select(FacebookPost).order_by(FacebookPost.created_at.desc()).limit(50)
    )
    posts = result.scalars().all()

    return templates.TemplateResponse(
        "posts.html",
        {
            "request": request,
            "user": current_user,
            "posts": posts,
        },
    )


@router.get("/news", response_class=HTMLResponse)
async def admin_news(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_auth),
):
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
            "user": current_user,
            "articles": articles,
        },
    )


@router.get("/alerts", response_class=HTMLResponse)
async def admin_alerts(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_auth),
):
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
            "user": current_user,
            "alerts": alerts,
        },
    )


@router.get("/tasks", response_class=HTMLResponse)
async def admin_tasks(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_auth),
):
    result = await db.execute(
        select(TaskLog)
        .order_by(TaskLog.started_at.desc())
        .limit(50)
    )
    tasks = result.scalars().all()

    return templates.TemplateResponse(
        "tasks.html",
        {
            "request": request,
            "user": current_user,
            "tasks": tasks,
        },
    )


@router.get("/audit-logs", response_class=HTMLResponse)
async def admin_audit_logs(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_auth),
):
    result = await db.execute(
        select(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .limit(50)
    )
    logs = result.scalars().all()

    return templates.TemplateResponse(
        "audit_logs.html",
        {
            "request": request,
            "user": current_user,
            "logs": logs,
        },
    )