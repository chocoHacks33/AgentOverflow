import asyncio
import math
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import get_es
from app.models.escalation import (
    EscalationBackend,
    EscalationConfigPublic,
    EscalationCreateRequest,
    EscalationListResponse,
    EscalationPublic,
    EscalationStatus,
)
from app.services.devin import create_devin_session, devin_enabled
from app.utils.auth import get_current_user

router = APIRouter(prefix="/escalations", tags=["escalations"])

PAGE_SIZE = 20


def _hit_to_escalation(hit: dict) -> EscalationPublic:
    src = hit["_source"]
    return EscalationPublic(id=hit["_id"], **src)


def _build_devin_prompt(question: dict, reason: str, repo: str | None) -> str:
    repo_line = f"Repo: {repo}" if repo else "Repo: not supplied. Ask for repo access if needed."
    return f"""You are Devin, solving a long-horizon coding task escalated from AgentOverflow.

AgentOverflow is a shared memory layer for coding agents. Fast agents search existing verified fixes first.
This task was escalated because agents could not confidently resolve it.

{repo_line}

Question:
{question["title"]}

Failure / context:
{question["body"]}

Escalation reason:
{reason}

Task:
1. Reproduce or reason through the failure.
2. Prefer a minimal patch.
3. Run relevant tests when repository access is available.
4. Return a concise reusable answer for future coding agents.
5. If you open a PR, include the PR link and test evidence.
"""


@router.get("/config", response_model=EscalationConfigPublic)
async def escalation_config():
    enabled = devin_enabled()
    return EscalationConfigPublic(
        devin_enabled=enabled,
        active_backend=EscalationBackend.devin if enabled else EscalationBackend.human,
        reason=(
            "DEVIN_API_KEY and DEVIN_ORG_ID detected; escalations can create Devin sessions."
            if enabled
            else "Devin is not configured; escalations route to the human mentor queue."
        ),
    )


@router.get("", response_model=EscalationListResponse)
async def list_escalations(page: int = Query(1, ge=1)):
    es = get_es()
    from_ = (page - 1) * PAGE_SIZE
    result = await es.search(
        index="escalations",
        query={"match_all": {}},
        sort=[{"created_at": {"order": "desc"}}],
        from_=from_,
        size=PAGE_SIZE,
    )
    total = result["hits"]["total"]["value"]
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    return EscalationListResponse(
        escalations=[_hit_to_escalation(hit) for hit in result["hits"]["hits"]],
        page=page,
        total_pages=total_pages,
    )


@router.post("/questions/{question_id}", response_model=EscalationPublic, status_code=201)
async def create_escalation(
    question_id: str,
    body: EscalationCreateRequest,
    user: dict = Depends(get_current_user),
):
    es = get_es()

    try:
        question = await es.get(index="questions", id=question_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Question not found")

    question_src = question["_source"]
    now = datetime.now(timezone.utc).isoformat()
    should_use_devin = body.requested_backend in {EscalationBackend.auto, EscalationBackend.devin} and devin_enabled()

    backend = EscalationBackend.human
    status = EscalationStatus.queued_for_human
    provider_message = "Queued for human mentor escalation because Devin is not configured."
    devin_session_id = None
    devin_session_url = None
    devin_status = None
    devin_error = None

    if body.requested_backend == EscalationBackend.devin and not devin_enabled():
        provider_message = "Devin was requested, but DEVIN_API_KEY and DEVIN_ORG_ID are missing. Queued for humans."

    if should_use_devin:
        backend = EscalationBackend.devin
        prompt = _build_devin_prompt(question_src, body.reason, body.repo)
        try:
            session = await asyncio.to_thread(
                create_devin_session,
                prompt=prompt,
                title=f"AgentOverflow escalation: {question_src['title']}",
                repo=body.repo,
            )
            status = EscalationStatus.sent_to_devin
            provider_message = "Created a Devin session for this long-horizon task."
            devin_session_id = session.session_id
            devin_session_url = session.url
            devin_status = session.status
        except Exception as exc:
            backend = EscalationBackend.human
            status = EscalationStatus.devin_failed_human_queue
            provider_message = "Devin escalation failed, so this was routed to human mentors."
            devin_error = str(exc)

    escalation_doc = {
        "question_id": question_id,
        "question_title": question_src["title"],
        "question_body": question_src["body"],
        "forum_name": question_src["forum_name"],
        "requester_id": user["id"],
        "requester_username": user["username"],
        "reason": body.reason,
        "repo": body.repo,
        "backend": backend.value,
        "status": status.value,
        "provider_message": provider_message,
        "devin_session_id": devin_session_id,
        "devin_session_url": devin_session_url,
        "devin_status": devin_status,
        "devin_error": devin_error,
        "created_at": now,
        "updated_at": now,
    }
    result = await es.index(index="escalations", document=escalation_doc, refresh="wait_for")
    return EscalationPublic(id=result["_id"], **escalation_doc)
