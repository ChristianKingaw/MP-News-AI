import uuid
from datetime import datetime
from pydantic import BaseModel

from app.models.task_log import TaskStatus as TaskLogStatus


class TaskLogResponse(BaseModel):
    id: uuid.UUID
    task_name: str
    status: TaskLogStatus
    started_at: datetime
    finished_at: datetime | None
    error_message: str | None
    items_processed: int

    model_config = {"from_attributes": True}


class TaskLogList(BaseModel):
    items: list[TaskLogResponse]
    total: int
    page: int
    page_size: int