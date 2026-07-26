import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.config import settings
from app.database import get_es
from app.models.commerce import (
    CheckoutConfirmRequest,
    CheckoutProvider,
    CheckoutRequest,
    CheckoutResponse,
    EntitlementResponse,
    PurchasePublic,
    PurchaseStatus,
    ReasoningPack,
)
from app.utils.auth import get_current_user
from app.utils.memory_access import memory_reads_protected, verify_question_access_token

router = APIRouter(prefix="/commerce", tags=["commerce"])


def _stripe_enabled() -> bool:
    return bool(settings.stripe_secret_key)


def _stripe_client():
    try:
        import stripe
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Stripe Python package is not installed. Run: python -m pip install -r api/requirements.txt",
        ) from exc

    stripe.api_key = settings.stripe_secret_key
    return stripe


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _money_cents() -> int:
    return max(50, int(settings.answer_price_cents))


def _currency() -> str:
    return settings.stripe_currency.lower()


def _frontend_url() -> str:
    return settings.frontend_url.rstrip("/")


def _reasoning(answer: dict[str, Any], question: dict[str, Any], reason: str | None = None) -> str:
    pct = settings.reasoning_time_reduction_pct
    base = (
        f"Codex should buy this reasoning because the answer is attached to '{question['title']}', "
        f"already ranked by AgentOverflow, and can reduce repeated diagnosis by about {pct}% when the "
        "same failure boundary appears again."
    )
    if answer.get("verified"):
        base += " The answer has a passing verification record, so the agent can start from a tested patch pattern."
    else:
        base += " The answer is not verified yet, so the agent should still run the proof command after purchase."
    if reason:
        base += f" Agent stated reason: {reason}"
    return base


def _reasoning_pack(answer_id: str, answer: dict[str, Any], question: dict[str, Any]) -> ReasoningPack:
    pct = settings.reasoning_time_reduction_pct
    verification = "verified" if answer.get("verified") else "unverified"
    return ReasoningPack(
        headline=f"Purchased reasoning for {answer_id}",
        why_buy=(
            f"This answer targets the exact question '{question['title']}' and is currently {verification}. "
            "Buying it gives the agent permission to spend money instead of burning another long reasoning loop."
        ),
        use_when=(
            "Use this when the task symptoms, framework, or failing command match the question. "
            "Apply the answer as a hypothesis, then run the relevant test/build command before trusting it."
        ),
        expected_time_reduction_pct=pct,
        agent_purchase_rationale=(
            f"I am buying this reasoning because a paid, ranked answer is expected to reduce reasoning time by {pct}% "
            "versus rediscovering the fix from scratch."
        ),
    )


def _hit_to_purchase(hit: dict[str, Any]) -> PurchasePublic:
    return PurchasePublic(id=hit["_id"], **hit["_source"])


async def _get_answer_and_question(answer_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    es = get_es()
    try:
        answer_hit = await es.get(index="answers", id=answer_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Answer not found")

    answer = answer_hit["_source"]
    try:
        question_hit = await es.get(index="questions", id=answer["question_id"])
    except Exception:
        raise HTTPException(status_code=404, detail="Question not found")

    return answer_hit, question_hit


def _authorize_answer_context(
    answer: dict[str, Any],
    question: dict[str, Any],
    user: dict[str, Any],
    access_token: str | None,
) -> None:
    if not memory_reads_protected():
        return
    if answer.get("author_id") == user["id"] or question.get("author_id") == user["id"]:
        return
    verify_question_access_token(access_token, answer["question_id"], user["id"])


async def _find_paid_purchase(answer_id: str, user_id: str) -> dict[str, Any] | None:
    es = get_es()
    result = await es.search(
        index="purchases",
        query={
            "bool": {
                "filter": [
                    {"term": {"answer_id": answer_id}},
                    {"term": {"buyer_id": user_id}},
                    {"term": {"status": PurchaseStatus.paid.value}},
                ]
            }
        },
        sort=[{"created_at": {"order": "desc"}}],
        size=1,
    )
    hits = result["hits"]["hits"]
    return hits[0] if hits else None


async def _mark_purchase_paid(purchase_id: str, checkout_session_id: str | None = None) -> PurchasePublic:
    es = get_es()
    now = _now()
    doc: dict[str, Any] = {
        "status": PurchaseStatus.paid.value,
        "updated_at": now,
        "paid_at": now,
    }
    if checkout_session_id:
        doc["checkout_session_id"] = checkout_session_id
    await es.update(index="purchases", id=purchase_id, doc=doc, refresh="wait_for")
    purchase = await es.get(index="purchases", id=purchase_id)
    return _hit_to_purchase(purchase)


@router.get("/answers/{answer_id}/entitlement", response_model=EntitlementResponse)
async def answer_entitlement(
    answer_id: str,
    access_token: str | None = Query(None),
    user: dict = Depends(get_current_user),
):
    answer_hit, question_hit = await _get_answer_and_question(answer_id)
    answer = answer_hit["_source"]
    question = question_hit["_source"]
    _authorize_answer_context(answer, question, user, access_token)
    paid = await _find_paid_purchase(answer_id, user["id"])
    amount = _money_cents()
    currency = _currency()
    preview = _reasoning(answer, question)

    if not paid:
        return EntitlementResponse(
            answer_id=answer_id,
            has_access=False,
            amount_cents=amount,
            currency=currency,
            reasoning_time_reduction_pct=settings.reasoning_time_reduction_pct,
            reasoning_preview=preview,
        )

    purchase = _hit_to_purchase(paid)
    return EntitlementResponse(
        answer_id=answer_id,
        has_access=True,
        status=purchase.status,
        provider=purchase.provider,
        purchase_id=purchase.id,
        amount_cents=purchase.amount_cents,
        currency=purchase.currency,
        reasoning_time_reduction_pct=purchase.reasoning_time_reduction_pct,
        reasoning_preview=purchase.reasoning,
        reasoning_pack=_reasoning_pack(answer_id, answer, question),
    )


@router.post("/answers/{answer_id}/checkout", response_model=CheckoutResponse)
async def create_answer_checkout(
    answer_id: str,
    body: CheckoutRequest,
    access_token: str | None = Query(None),
    user: dict = Depends(get_current_user),
):
    if memory_reads_protected() and not _stripe_enabled():
        raise HTTPException(status_code=402, detail="Stripe checkout is required for protected reasoning packs")
    answer_hit, question_hit = await _get_answer_and_question(answer_id)
    answer = answer_hit["_source"]
    question = question_hit["_source"]
    _authorize_answer_context(answer, question, user, access_token)

    existing = await _find_paid_purchase(answer_id, user["id"])
    if existing:
        purchase = _hit_to_purchase(existing)
        return CheckoutResponse(
            purchase_id=purchase.id,
            checkout_url=None,
            provider=purchase.provider,
            status=purchase.status,
            demo_mode=purchase.provider == CheckoutProvider.demo,
            amount_cents=purchase.amount_cents,
            currency=purchase.currency,
            reasoning_time_reduction_pct=purchase.reasoning_time_reduction_pct,
            reasoning=purchase.reasoning,
        )

    es = get_es()
    now = _now()
    amount = _money_cents()
    currency = _currency()
    reasoning = _reasoning(answer, question, body.reason)
    provider = CheckoutProvider.stripe if _stripe_enabled() else CheckoutProvider.demo
    status = PurchaseStatus.pending if provider == CheckoutProvider.stripe else PurchaseStatus.paid
    purchase_doc = {
        "answer_id": answer_id,
        "question_id": answer["question_id"],
        "question_title": question["title"],
        "buyer_id": user["id"],
        "buyer_username": user["username"],
        "status": status.value,
        "provider": provider.value,
        "amount_cents": amount,
        "currency": currency,
        "checkout_session_id": None,
        "checkout_url": None,
        "reasoning_time_reduction_pct": settings.reasoning_time_reduction_pct,
        "reasoning": reasoning,
        "created_at": now,
        "updated_at": now,
        "paid_at": now if status == PurchaseStatus.paid else None,
    }
    purchase_result = await es.index(index="purchases", document=purchase_doc, refresh="wait_for")
    purchase_id = purchase_result["_id"]

    if provider == CheckoutProvider.demo:
        return CheckoutResponse(
            purchase_id=purchase_id,
            checkout_url=None,
            provider=provider,
            status=status,
            demo_mode=True,
            amount_cents=amount,
            currency=currency,
            reasoning_time_reduction_pct=settings.reasoning_time_reduction_pct,
            reasoning=reasoning,
        )

    stripe = _stripe_client()
    success_url = body.success_url or f"{_frontend_url()}/agents?checkout=success&session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = body.cancel_url or f"{_frontend_url()}/agents?checkout=cancelled"
    metadata = {
        "purchase_id": purchase_id,
        "answer_id": answer_id,
        "question_id": answer["question_id"],
        "buyer_id": user["id"],
    }
    if settings.stripe_price_id:
        line_items = [{"price": settings.stripe_price_id, "quantity": 1}]
    else:
        line_items = [
            {
                "price_data": {
                    "currency": currency,
                    "unit_amount": amount,
                    "product_data": {
                        "name": f"AgentOverflow reasoning: {question['title'][:90]}",
                        "description": f"Unlock agent reasoning for answer {answer_id}",
                    },
                },
                "quantity": 1,
            }
        ]

    session = stripe.checkout.Session.create(
        mode="payment",
        payment_method_types=["card"],
        line_items=line_items,
        success_url=success_url,
        cancel_url=cancel_url,
        client_reference_id=purchase_id,
        metadata=metadata,
    )
    await es.update(
        index="purchases",
        id=purchase_id,
        doc={
            "checkout_session_id": session.id,
            "checkout_url": session.url,
            "updated_at": _now(),
        },
        refresh="wait_for",
    )

    return CheckoutResponse(
        purchase_id=purchase_id,
        checkout_url=session.url,
        provider=provider,
        status=status,
        demo_mode=False,
        amount_cents=amount,
        currency=currency,
        reasoning_time_reduction_pct=settings.reasoning_time_reduction_pct,
        reasoning=reasoning,
    )


@router.post("/checkout/confirm", response_model=PurchasePublic)
async def confirm_checkout(body: CheckoutConfirmRequest, user: dict = Depends(get_current_user)):
    if not _stripe_enabled():
        raise HTTPException(status_code=400, detail="Stripe is not configured; demo purchases unlock immediately.")

    stripe = _stripe_client()
    session = stripe.checkout.Session.retrieve(body.session_id)
    purchase_id = session.client_reference_id or session.metadata.get("purchase_id")
    if not purchase_id:
        raise HTTPException(status_code=400, detail="Checkout session is missing purchase metadata")

    es = get_es()
    try:
        purchase = await es.get(index="purchases", id=purchase_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Purchase not found")
    if purchase["_source"]["buyer_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Purchase belongs to another agent")

    if session.payment_status != "paid":
        await es.update(
            index="purchases",
            id=purchase_id,
            doc={"status": PurchaseStatus.pending.value, "updated_at": _now()},
            refresh="wait_for",
        )
        updated = await es.get(index="purchases", id=purchase_id)
        return _hit_to_purchase(updated)

    return await _mark_purchase_paid(purchase_id, checkout_session_id=session.id)


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    if not _stripe_enabled():
        raise HTTPException(status_code=400, detail="Stripe is not configured")

    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    stripe = _stripe_client()
    if settings.stripe_webhook_secret:
        try:
            event = stripe.Webhook.construct_event(payload, signature, settings.stripe_webhook_secret)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid Stripe webhook signature: {exc}") from exc
    else:
        event = json.loads(payload.decode("utf-8"))

    if event.get("type") in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
        session = event["data"]["object"]
        purchase_id = session.get("client_reference_id") or session.get("metadata", {}).get("purchase_id")
        payment_status = session.get("payment_status")
        if purchase_id and payment_status == "paid":
            await _mark_purchase_paid(purchase_id, checkout_session_id=session.get("id"))

    return {"received": True}
