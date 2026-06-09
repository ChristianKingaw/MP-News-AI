from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.post import FacebookPost, PostStatus
from app.schemas.post import (
    FacebookPostResponse,
    FacebookPostList,
    FacebookPostUpdate,
)

router = APIRouter(prefix="/posts", tags=["facebook-posts"])


@router.get("", response_model=FacebookPostList)
async def list_posts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: PostStatus | None = None,
    db: AsyncSession = Depends(get_db),
):
    conditions = []
    if status:
        conditions.append(FacebookPost.status == status)

    count_q = select(func.count(FacebookPost.id))
    if conditions:
        count_q = count_q.where(*conditions)
    total = (await db.execute(count_q)).scalar() or 0

    query = select(FacebookPost).order_by(FacebookPost.created_at.desc())
    if conditions:
        query = query.where(*conditions)
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = result.scalars().all()

    return FacebookPostList(
        items=[FacebookPostResponse.model_validate(p) for p in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{post_id}", response_model=FacebookPostResponse)
async def get_post(post_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(FacebookPost).where(FacebookPost.id == post_id)
    )
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return FacebookPostResponse.model_validate(post)


@router.patch("/{post_id}", response_model=FacebookPostResponse)
async def update_post(
    post_id: str,
    post_data: FacebookPostUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(FacebookPost).where(FacebookPost.id == post_id)
    )
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    update_dict = post_data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(post, key, value)

    db.add(post)
    await db.flush()
    await db.refresh(post)
    return FacebookPostResponse.model_validate(post)


@router.post("/{post_id}/publish", response_model=FacebookPostResponse)
async def publish_post(post_id: str, db: AsyncSession = Depends(get_db)):
    from app.services.facebook_service import facebook_service
    from datetime import datetime

    result = await db.execute(
        select(FacebookPost).where(FacebookPost.id == post_id)
    )
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    publish_result = await facebook_service.publish_post(
        post.caption, post.image_path
    )

    if publish_result["error"]:
        post.status = PostStatus.FAILED
        post.error_message = publish_result["error"]
    else:
        post.status = PostStatus.PUBLISHED
        post.fb_post_id = publish_result["fb_post_id"]
        post.fb_post_url = publish_result["fb_post_url"]
        post.published_at = datetime.utcnow()

    db.add(post)
    await db.flush()
    await db.refresh(post)
    return FacebookPostResponse.model_validate(post)