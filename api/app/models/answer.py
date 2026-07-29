from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AnswerCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(..., min_length=1, max_length=50000)


class AnswerPublic(BaseModel):
    id: str
    body: str
    question_id: str
    author_id: str
    author_username: str
    upvote_count: int = 0
    downvote_count: int = 0
    score: int = 0
    created_at: datetime
    user_vote: str | None = None
    verification_status: str = "unverified"
    verified: bool = False
    verification_engine: str | None = None
    verification_output: str = ""
    verification_error: str = ""
    verification_exit_code: int | None = None
    verification_seconds: float | None = None
    verified_at: datetime | None = None


class AnswerListResponse(BaseModel):
    answers: list[AnswerPublic]
    page: int
    total_pages: int
