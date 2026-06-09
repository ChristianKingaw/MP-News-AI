import uuid
from datetime import datetime
from pydantic import BaseModel
from app.models.news import SourceType, ArticleStatus


class NewsArticleBase(BaseModel):
    source_type: SourceType
    source_url: str | None = None
    title: str
    content: str


class NewsArticleCreate(NewsArticleBase):
    pass


class NewsArticleUpdate(BaseModel):
    summary: str | None = None
    keywords_matched: str | None = None
    is_disaster_related: bool | None = None
    status: ArticleStatus | None = None


class NewsArticleResponse(NewsArticleBase):
    id: uuid.UUID
    summary: str | None = None
    keywords_matched: str | None = None
    is_disaster_related: bool
    status: ArticleStatus
    fetched_at: datetime
    processed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NewsArticleList(BaseModel):
    items: list[NewsArticleResponse]
    total: int
    page: int
    page_size: int