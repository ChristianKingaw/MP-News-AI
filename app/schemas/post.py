import uuid
from datetime import datetime
from pydantic import BaseModel
from app.models.post import PostStatus


class FacebookPostBase(BaseModel):
    article_id: uuid.UUID | None = None
    alert_id: uuid.UUID | None = None
    caption: str
    summary: str | None = None


class FacebookPostCreate(FacebookPostBase):
    pass


class FacebookPostUpdate(BaseModel):
    caption: str | None = None
    summary: str | None = None
    status: PostStatus | None = None
    image_prompt: str | None = None


class FacebookPostResponse(FacebookPostBase):
    id: uuid.UUID
    image_prompt: str | None = None
    image_url: str | None = None
    image_path: str | None = None
    status: PostStatus
    retry_count: int
    last_error: str | None = None
    fb_post_id: str | None = None
    fb_post_url: str | None = None
    published_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FacebookPostList(BaseModel):
    items: list[FacebookPostResponse]
    total: int
    page: int
    page_size: int