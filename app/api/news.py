from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.news import NewsArticle, ArticleStatus, SourceType
from app.schemas.news import (
    NewsArticleResponse,
    NewsArticleList,
    NewsArticleUpdate,
)

router = APIRouter(prefix="/news", tags=["news-articles"])


@router.get("", response_model=NewsArticleList)
async def list_articles(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: ArticleStatus | None = None,
    is_disaster_related: bool | None = None,
    source_type: SourceType | None = None,
    db: AsyncSession = Depends(get_db),
):
    conditions = []
    if status:
        conditions.append(NewsArticle.status == status)
    if is_disaster_related is not None:
        conditions.append(NewsArticle.is_disaster_related == is_disaster_related)
    if source_type:
        conditions.append(NewsArticle.source_type == source_type)

    count_q = select(func.count(NewsArticle.id))
    if conditions:
        count_q = count_q.where(*conditions)
    total = (await db.execute(count_q)).scalar() or 0

    query = select(NewsArticle).order_by(NewsArticle.fetched_at.desc())
    if conditions:
        query = query.where(*conditions)
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = result.scalars().all()

    return NewsArticleList(
        items=[NewsArticleResponse.model_validate(a) for a in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{article_id}", response_model=NewsArticleResponse)
async def get_article(article_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(NewsArticle).where(NewsArticle.id == article_id)
    )
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return NewsArticleResponse.model_validate(article)


@router.patch("/{article_id}", response_model=NewsArticleResponse)
async def update_article(
    article_id: str,
    article_data: NewsArticleUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(NewsArticle).where(NewsArticle.id == article_id)
    )
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    update_dict = article_data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(article, key, value)

    db.add(article)
    await db.flush()
    await db.refresh(article)
    return NewsArticleResponse.model_validate(article)


@router.post("/{article_id}/process", response_model=dict)
async def process_article(article_id: str, db: AsyncSession = Depends(get_db)):
    from app.services.alert_service import process_article_workflow

    post = await process_article_workflow(db, article_id)
    if not post:
        raise HTTPException(status_code=404, detail="Article not found")
    await db.flush()
    return {"status": "processed", "post_id": str(post.id)}