import uuid
from datetime import datetime
from pydantic import BaseModel

from app.models.audit import AuditAction


class AuditLogResponse(BaseModel):
    id: uuid.UUID
    action: AuditAction
    entity_type: str
    entity_id: str | None
    performed_by: str
    details: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditLogList(BaseModel):
    items: list[AuditLogResponse]
    total: int
    page: int
    page_size: int