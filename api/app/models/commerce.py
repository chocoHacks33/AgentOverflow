from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class PurchaseStatus(str, Enum):
    pending = "pending"
    paid = "paid"
    failed = "failed"
    canceled = "canceled"


class CheckoutProvider(str, Enum):
    stripe = "stripe"
    demo = "demo"


class CheckoutRequest(BaseModel):
    success_url: str | None = None
    cancel_url: str | None = None
    reason: str | None = Field(default=None, max_length=1000)


class CheckoutConfirmRequest(BaseModel):
    session_id: str


class ReasoningPack(BaseModel):
    headline: str
    why_buy: str
    use_when: str
    expected_time_reduction_pct: int = 50
    agent_purchase_rationale: str


class PurchasePublic(BaseModel):
    id: str
    answer_id: str
    question_id: str
    question_title: str
    buyer_id: str
    buyer_username: str
    status: PurchaseStatus
    provider: CheckoutProvider
    amount_cents: int
    currency: str
    checkout_session_id: str | None = None
    checkout_url: str | None = None
    reasoning_time_reduction_pct: int = 50
    reasoning: str
    created_at: datetime
    updated_at: datetime
    paid_at: datetime | None = None


class CheckoutResponse(BaseModel):
    purchase_id: str
    checkout_url: str | None = None
    provider: CheckoutProvider
    status: PurchaseStatus
    demo_mode: bool = False
    amount_cents: int
    currency: str
    reasoning_time_reduction_pct: int
    reasoning: str


class EntitlementResponse(BaseModel):
    answer_id: str
    has_access: bool
    status: PurchaseStatus | None = None
    provider: CheckoutProvider | None = None
    purchase_id: str | None = None
    amount_cents: int
    currency: str
    reasoning_time_reduction_pct: int
    reasoning_preview: str
    reasoning_pack: ReasoningPack | None = None
