import uuid
from datetime import datetime
from pydantic import BaseModel
from app.models.alert import AlertType, AlertSeverity, AlertStatus


class DisasterAlertBase(BaseModel):
    alert_type: AlertType
    severity: AlertSeverity = AlertSeverity.INFO
    title: str
    description: str
    location: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    source: str | None = None
    source_url: str | None = None


class DisasterAlertCreate(DisasterAlertBase):
    pass


class DisasterAlertUpdate(BaseModel):
    severity: AlertSeverity | None = None
    title: str | None = None
    description: str | None = None
    status: AlertStatus | None = None


class DisasterAlertResponse(DisasterAlertBase):
    id: uuid.UUID
    status: AlertStatus
    reported_at: datetime
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DisasterAlertList(BaseModel):
    items: list[DisasterAlertResponse]
    total: int
    page: int
    page_size: int