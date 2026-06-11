import uuid
import enum
from datetime import datetime
from sqlalchemy import String, Text, DateTime, Enum, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class AuditAction(str, enum.Enum):
    APPROVED_POST = "approved_post"
    REJECTED_POST = "rejected_post"
    PUBLISHED_POST = "published_post"
    APPROVED_ARTICLE = "approved_article"
    REJECTED_ARTICLE = "rejected_article"
    CREATED_ALERT = "created_alert"
    UPDATED_ALERT = "updated_alert"
    RESOLVED_ALERT = "resolved_alert"
    MANUAL_PUBLISH = "manual_publish"
    SETTINGS_CHANGED = "settings_changed"
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    action: Mapped[AuditAction] = mapped_column(
        Enum(AuditAction, name="audit_action_enum"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    performed_by: Mapped[str] = mapped_column(String(128), nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )