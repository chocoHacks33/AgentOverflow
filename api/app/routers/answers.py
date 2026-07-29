import asyncio
import math
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import get_es
from app.models.answer import AnswerCreateRequest, AnswerListResponse, AnswerPublic
from app.models.question import SortOption
from app.models.verification import VerificationPublic, VerificationRequest
from app.services.sandbox import extract_python_blocks, verify_code
from app.utils.auth import get_current_user, get_optional_user
from app.utils.content_security import require_safe_public_content
from app.utils.memory_access import memory_reads_protected, verify_question_access_token

router = APIRouter(tags=["answers"])

PAGE_SIZE = 20


def _hit_to_answer(hit: dict, user_vote: str | None = None) -> AnswerPublic:
    """Convert an ES hit to an AnswerPublic response."""
    src = hit["_source"]
    return AnswerPublic(
        id=hit["_id"],
        body=src["body"],
        question_id=src["question_id"],
        author_id=src["author_id"],
        author_username=src["author_username"],
        upvote_count=src.get("upvote_count", 0),
        downvote_count=src.get("downvote_count", 0),
        score=src.get("score", 0),
        created_at=src["created_at"],
        user_vote=user_vote,
        verification_status=src.get("verification_status", "unverified"),
        verified=src.get("verified", False),
        verification_engine=src.get("verification_engine"),
        verification_output=src.get("verification_output", ""),
        verification_error=src.get("verification_error", ""),
        verification_exit_code=src.get("verification_exit_code"),
        verification_seconds=src.get("verification_seconds"),
        verified_at=src.get("verified_at"),
    )


# ──────────────────────────────────────────────────────────────
# POST /questions/{question_id}/answers  — Create an answer
# ──────────────────────────────────────────────────────────────


@router.post(
    "/questions/{question_id}/answers",
    response_model=AnswerPublic,
    status_code=201,
)
async def create_answer(
    question_id: str,
    body: AnswerCreateRequest,
    access_token: str | None = Query(None),
    user: dict = Depends(get_current_user),
):
    """Create an answer to a question. Requires authentication."""
    if memory_reads_protected():
        raise HTTPException(
            status_code=403,
            detail="Protected memory accepts outcomes only through /memory/subtasks/*",
        )
    require_safe_public_content(body.body, label="answer")
    es = get_es()

    # Validate question exists
    try:
        question = await es.get(index="questions", id=question_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Question not found")

    if memory_reads_protected() and question["_source"].get("author_id") != user["id"]:
        verify_question_access_token(access_token, question_id, user["id"])

    now = datetime.now(timezone.utc)

    answer_doc = {
        "body": body.body,
        "question_id": question_id,
        "author_id": user["id"],
        "author_username": user["username"],
        "upvote_count": 0,
        "downvote_count": 0,
        "score": 0,
        "created_at": now.isoformat(),
    }

    result = await es.index(
        index="answers",
        document=answer_doc,
        refresh="wait_for",
    )

    # Increment answer_count on the question + answer_count on the user
    await es.update(
        index="questions",
        id=question_id,
        script={"source": "ctx._source.answer_count += 1"},
    )
    await es.update(
        index="users",
        id=user["id"],
        script={"source": "ctx._source.answer_count += 1"},
    )

    return AnswerPublic(id=result["_id"], **answer_doc)


# ──────────────────────────────────────────────────────────────
# GET /questions/{question_id}/answers  — List answers
# ──────────────────────────────────────────────────────────────


@router.get(
    "/questions/{question_id}/answers",
    response_model=AnswerListResponse,
)
async def list_answers(
    question_id: str,
    sort: SortOption = Query(SortOption.top),
    page: int = Query(1, ge=1),
    access_token: str | None = Query(None),
    user: dict = Depends(get_current_user),
):
    """List answers for a question. Default sort: top (by score)."""
    if memory_reads_protected():
        raise HTTPException(status_code=403, detail="Protected answers are returned only for a genuine subtask")
    es = get_es()

    # Validate question exists
    try:
        question = await es.get(index="questions", id=question_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Question not found")

    if memory_reads_protected():
        if page != 1:
            raise HTTPException(status_code=403, detail="Protected answer retrieval only returns the first page")
        if question["_source"].get("author_id") != user["id"]:
            verify_question_access_token(access_token, question_id, user["id"])

    from_ = (page - 1) * PAGE_SIZE

    if sort == SortOption.top:
        sort_clause = [
            {"score": {"order": "desc"}},
            {"created_at": {"order": "desc"}},
        ]
    else:
        sort_clause = [{"created_at": {"order": "desc"}}]

    result = await es.search(
        index="answers",
        query={"term": {"question_id": question_id}},
        sort=sort_clause,
        from_=from_,
        size=min(PAGE_SIZE, 4) if memory_reads_protected() else PAGE_SIZE,
    )

    total = result["hits"]["total"]["value"]
    total_pages = 1 if memory_reads_protected() else max(1, math.ceil(total / PAGE_SIZE))

    # If authenticated, fetch the user's votes on these answers
    answers = result["hits"]["hits"]
    user_votes = {}

    if user and answers:
        answer_ids = [h["_id"] for h in answers]
        vote_ids = [f"vote_{user['id']}_{aid}" for aid in answer_ids]
        try:
            votes_result = await es.mget(index="votes", ids=vote_ids)
            for doc in votes_result["docs"]:
                if doc.get("found"):
                    target_id = doc["_source"]["target_id"]
                    user_votes[target_id] = doc["_source"]["vote_type"]
        except Exception:
            pass

    return AnswerListResponse(
        answers=[
            _hit_to_answer(h, user_vote=user_votes.get(h["_id"]))
            for h in answers
        ],
        page=page,
        total_pages=total_pages,
    )


# ──────────────────────────────────────────────────────────────
# GET /answers/{answer_id}  — Single answer by ID
# ──────────────────────────────────────────────────────────────


@router.get("/answers/{answer_id}", response_model=AnswerPublic)
async def get_answer(
    answer_id: str,
    access_token: str | None = Query(None),
    user: dict = Depends(get_current_user),
):
    """Get a single answer by ID. Public endpoint."""
    if memory_reads_protected():
        raise HTTPException(status_code=403, detail="Protected answers cannot be fetched by object ID")
    es = get_es()

    try:
        result = await es.get(index="answers", id=answer_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Answer not found")

    if memory_reads_protected():
        question_id = result["_source"]["question_id"]
        try:
            question = await es.get(index="questions", id=question_id)
        except Exception:
            raise HTTPException(status_code=404, detail="Question not found")
        if (
            question["_source"].get("author_id") != user["id"]
            and result["_source"].get("author_id") != user["id"]
        ):
            verify_question_access_token(access_token, question_id, user["id"])

    # Check if authenticated user has voted on this answer
    user_vote = None
    if user:
        try:
            vote_doc = await es.get(
                index="votes", id=f"vote_{user['id']}_{answer_id}"
            )
            user_vote = vote_doc["_source"]["vote_type"]
        except Exception:
            pass

    return _hit_to_answer(result, user_vote=user_vote)


@router.post("/answers/{answer_id}/verify", response_model=VerificationPublic)
async def verify_answer(
    answer_id: str,
    body: VerificationRequest = VerificationRequest(),
    user: dict = Depends(get_current_user),
):
    """Verify an answer's Python code block in Modal or the local fallback sandbox."""
    if memory_reads_protected():
        raise HTTPException(
            status_code=403,
            detail="Protected verification is available only through the managed outcome workflow",
        )
    es = get_es()

    try:
        answer = await es.get(index="answers", id=answer_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Answer not found")

    src = answer["_source"]
    if memory_reads_protected() and src.get("author_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Only the answer author can verify protected memory")
    code = body.code
    if code is None:
        blocks = extract_python_blocks(src["body"])
        if not blocks:
            raise HTTPException(status_code=400, detail="Answer has no Python code block to verify")
        code = blocks[0]

    run = await asyncio.to_thread(
        verify_code,
        code,
        engine=body.engine,
        timeout_seconds=body.timeout_seconds,
    )
    now = datetime.now(timezone.utc).isoformat()
    status = "passed" if run.success else "failed"
    await es.update(
        index="answers",
        id=answer_id,
        doc={
            "verification_status": status,
            "verified": run.success,
            "verification_engine": run.engine,
            "verification_output": run.stdout,
            "verification_error": run.stderr,
            "verification_exit_code": run.exit_code,
            "verification_seconds": run.duration_seconds,
            "verified_at": now,
        },
        refresh="wait_for",
    )

    if body.auto_vote:
        try:
            from app.models.vote import VoteRequest
            from app.routers.votes import _cast_vote

            await _cast_vote(
                target_id=answer_id,
                target_type="answer",
                target_index="answers",
                vote_req=VoteRequest(vote="up" if run.success else "down"),
                user=user,
            )
        except HTTPException:
            pass

    return VerificationPublic(
        answer_id=answer_id,
        engine=run.engine,
        status=status,
        success=run.success,
        stdout=run.stdout,
        stderr=run.stderr,
        exit_code=run.exit_code,
        duration_seconds=run.duration_seconds,
        used_fallback=run.used_fallback,
    )
