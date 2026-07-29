from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ForumCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., min_length=1, max_length=250)
    description: str | None = Field(None, max_length=50000)


class ForumPublic(BaseModel):
    id: str
    name: str
    description: str | None = None
    created_by: str
    created_by_username: str
    question_count: int = 0
    created_at: datetime
