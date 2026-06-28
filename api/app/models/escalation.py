from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class EscalationBackend(str, Enum):
    auto = "auto"
    devin = "devin"
    human = "human"


class EscalationStatus(str, Enum):
    queued_for_human = "queued_for_human"
    sent_to_devin = "sent_to_devin"
    devin_failed_human_queue = "devin_failed_human_queue"
    resolved = "resolved"


class EscalationCreateRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=4000)
    repo: str | None = Field(default=None, max_length=300)
    requested_backend: EscalationBackend = EscalationBackend.auto


class EscalationPublic(BaseModel):
    id: str
    question_id: str
    question_title: str
    question_body: str
    forum_name: str
    requester_id: str
    requester_username: str
    reason: str
    repo: str | None = None
    backend: EscalationBackend
    status: EscalationStatus
    provider_message: str
    devin_session_id: str | None = None
    devin_session_url: str | None = None
    devin_status: str | None = None
    devin_error: str | None = None
    created_at: datetime
    updated_at: datetime


class EscalationListResponse(BaseModel):
    escalations: list[EscalationPublic]
    page: int
    total_pages: int


class EscalationConfigPublic(BaseModel):
    devin_enabled: bool
    active_backend: EscalationBackend
    reason: str
