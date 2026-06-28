from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class SortOption(str, Enum):
    newest = "newest"
    top = "top"


class QuestionCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=250)
    body: str = Field(..., min_length=1, max_length=50000)
    forum_id: str


class QuestionPublic(BaseModel):
    id: str
    title: str
    body: str
    forum_id: str
    forum_name: str
    author_id: str
    author_username: str
    upvote_count: int = 0
    downvote_count: int = 0
    score: int = 0
    answer_count: int = 0
    has_code: bool = False
    word_count: int = 0
    created_at: datetime
    user_vote: str | None = None


class QuestionListResponse(BaseModel):
    questions: list[QuestionPublic]
    page: int
    total_pages: int
