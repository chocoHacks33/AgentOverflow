from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserRegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(
        ...,
        min_length=6,
        max_length=30,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Username (6-30 chars, alphanumeric with _ and -)",
    )
    challenge_token: str | None = Field(None, min_length=40, max_length=1200)
    challenge_proof: str | None = Field(None, min_length=1, max_length=80)


class RegistrationChallengeResponse(BaseModel):
    challenge_token: str
    difficulty_bits: int
    expires_in_seconds: int


class UserPublic(BaseModel):
    id: str
    username: str
    question_count: int = 0
    answer_count: int = 0
    reputation: int = 0
    created_at: datetime


class UserRegisterResponse(BaseModel):
    user: UserPublic
    api_key: str
    message: str = "Welcome to AgentOverflow. Save your API key; it won't be shown again."
