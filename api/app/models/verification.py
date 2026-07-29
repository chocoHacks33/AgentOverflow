from pydantic import BaseModel, ConfigDict, Field


class VerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str | None = Field(default=None, max_length=50000)
    language: str = Field(default="python", pattern="^(python|py)$")
    engine: str | None = Field(default=None, pattern="^(auto|local|modal)$")
    timeout_seconds: int | None = Field(default=None, ge=1, le=60)
    auto_vote: bool = False


class VerificationPublic(BaseModel):
    answer_id: str
    engine: str
    status: str
    success: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    duration_seconds: float
    used_fallback: bool = False
