from enum import Enum

from pydantic import BaseModel


class VoteType(str, Enum):
    up = "up"
    down = "down"
    none = "none"


class VoteRequest(BaseModel):
    vote: VoteType


class VoteResponse(BaseModel):
    vote: str
    upvote_count: int
    downvote_count: int
    score: int
