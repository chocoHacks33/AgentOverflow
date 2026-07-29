from enum import Enum

from pydantic import BaseModel, ConfigDict


class VoteType(str, Enum):
    up = "up"
    down = "down"
    none = "none"


class VoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vote: VoteType


class VoteResponse(BaseModel):
    vote: str
    upvote_count: int
    downvote_count: int
    score: int
    trusted: bool = False
    trust_reason: str = "Outcome recorded without independent ranking weight"
