import uuid
from datetime import datetime
from pydantic import BaseModel


class SystemSettingResponse(BaseModel):
    id: uuid.UUID
    key: str
    value: str
    description: str | None
    updated_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class SystemSettingCreate(BaseModel):
    key: str
    value: str
    description: str | None = None


class SystemSettingUpdate(BaseModel):
    value: str
    description: str | None = None


class SystemSettingList(BaseModel):
    items: list[SystemSettingResponse]
    total: int
    page: int
    page_size: int