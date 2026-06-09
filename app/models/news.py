import uuid
import enum
from datetime import datetime
from sqlalchemy import String, Text, DateTime, Enum, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class SourceType(str, enum.Enum):
    PHIVOLCS = "phivolcs"
    NEWS_API = "news_api"
    RSS_FEED = "rss_feed"
    MANUAL = "manual"


class ArticleStatus(str, enum.Enum):
    RAW = "raw"
    FILTERED = "filtered"
    SUMMARIZED = "summarized"
    PUBLISHED = "published"
    REJECTED = "rejected"


class NewsArticle(Base):
    __tablename__ = "news_articles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, name="source_type_enum"), nullable=False
    )
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    keywords_matched: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_disaster_related: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[ArticleStatus] = mapped_column(
        Enum(ArticleStatus, name="article_status_enum"),
        default=ArticleStatus.RAW,
        nullable=False,
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )