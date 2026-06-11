import uuid
from datetime import datetime
from pydantic import BaseModel
from app.models.news import SourceType, ArticleStatus, RiskLevel


class NewsArticleBase(BaseModel):
    source_type: SourceType
    source_url: str | None = None
    title: str
    content: str


class NewsArticleCreate(NewsArticleBase):
    keywords_matched: str | None = None
    is_disaster_related: bool = True


class NewsArticleUpdate(BaseModel):
    summary: str | None = None
    keywords_matched: str | None = None
    is_disaster_related: bool | None = None
    status: ArticleStatus | None = None
    severity: RiskLevel | None = None
    affected_location: str | None = None
    location_relevance_score: float | None = None


class NewsArticleResponse(NewsArticleBase):
    id: uuid.UUID
    content_hash: str | None = None
    summary: str | None = None
    keywords_matched: str | None = None
    is_disaster_related: bool
    severity: RiskLevel | None = None
    affected_location: str | None = None
    location_relevance_score: float | None = None
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