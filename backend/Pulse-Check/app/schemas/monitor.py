from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


MonitorStatus = Literal["ACTIVE", "DOWN", "PAUSED"]


class MonitorCreate(BaseModel):
    id: str = Field(min_length=1, max_length=255)
    timeout: int = Field(gt=0)
    alert_email: EmailStr


class MonitorResponse(BaseModel):
    id: str
    timeout: int
    alert_email: EmailStr
    status: MonitorStatus

    created_at: datetime
    last_heartbeat_at: datetime
    expires_at: datetime

    model_config = ConfigDict(from_attributes=True)


class HeartbeatResponse(BaseModel):
    message: str
    id: str
    status: MonitorStatus
    expires_at: datetime


class PauseResponse(BaseModel):
    message: str
    id: str
    status: MonitorStatus
    remaining_seconds: float