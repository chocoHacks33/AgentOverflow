from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.database import get_es
from app.models.vote import VoteRequest, VoteResponse, VoteType
from app.utils.auth import get_current_user
from app.utils.memory_access import memory_reads_protected, verify_question_access_token
from app.utils.request_security import actor_key, client_network_key

router = APIRouter(tags=["votes"])


async def _cast_vote(
    target_id: str,
    target_type: str,
    target_index: str,
    vote_req: VoteRequest,
    user: dict,
    access_token: str | None = None,
    trusted_outcome: bool = False,
    request_network_hash: str | None = None,
    source_attempt_id: str | None = None,
) -> VoteResponse:
    """
    Shared voting logic for questions and answers.

    Uses deterministic document IDs (vote_{user_id}_{target_id}) so
    ES naturally enforces one-vote-per-user — same ID = same document.

    Vote state transitions:
    - No existing vote → up/down: INSERT vote, increment counter
    - Existing up → down: UPDATE vote, decrement up + increment down
    - Existing up → none: DELETE vote, decrement up
    - Existing vote → same vote: 409 conflict (already voted that way)
    """
    es = get_es()

    # Validate target exists
    try:
        target = await es.get(index=target_index, id=target_id)
    except Exception:
        raise HTTPException(status_code=404, detail=f"{target_type.title()} not found")

    target_src = target["_source"]
    if target_src.get("author_id") == user["id"]:
        raise HTTPException(status_code=403, detail="Agents cannot vote on their own content")

    if memory_reads_protected() and not trusted_outcome:
        if target_type == "question":
            if target_src.get("author_id") != user["id"]:
                verify_question_access_token(access_token, target_id, user["id"])
        elif target_type == "answer":
            question_id = target_src.get("question_id")
            try:
                question = await es.get(index="questions", id=question_id)
            except Exception:
                raise HTTPException(status_code=404, detail="Question not found")
            if (
                target_src.get("author_id") != user["id"]
                and question["_source"].get("author_id") != user["id"]
            ):
                verify_question_access_token(access_token, question_id, user["id"])

    vote_doc_id = f"vote_{user['id']}_{target_id}"
    new_vote = vote_req.vote

    protected = memory_reads_protected()
    reviewer_registration_network = user.get("registration_network_hash")
    publisher_network = target_src.get("publisher_network_hash")
    trust_reason = "Outcome recorded without independent ranking weight"
    ranking_eligible = not protected
    if protected and trusted_outcome:
        if target_type != "answer":
            trust_reason = "Only execution outcomes can affect protected ranking"
        elif target_src.get("schema_version") != "agentoverflow.execution.v3":
            trust_reason = "Legacy execution records cannot receive trusted ranking weight"
        elif target_src.get("provenance") != "agent_subtask_outcome":
            trust_reason = "Execution provenance is not eligible for trusted ranking"
        elif not source_attempt_id:
            trust_reason = "A bound subtask attempt is required for trusted ranking"
        elif not reviewer_registration_network or not request_network_hash or not publisher_network:
            trust_reason = "Independent identity provenance is incomplete"
        elif reviewer_registration_network == publisher_network:
            trust_reason = "Reviewer and publisher enrolled from the same independence cluster"
        elif request_network_hash == publisher_network:
            trust_reason = "Outcome was reported from the publisher's independence cluster"
        else:
            ranking_eligible = True
            trust_reason = "Independent task-bound outcome"

    cluster_key = reviewer_registration_network or user["id"]
    cluster_id = actor_key("outcome-cluster", target_id, cluster_key)
    if hasattr(es, "cast_vote_atomic"):
        result = await es.cast_vote_atomic(
            target_index=target_index,
            target_id=target_id,
            target_type=target_type,
            user_id=user["id"],
            vote_value=new_vote.value,
            vote_doc_id=vote_doc_id,
            ranking_eligible=ranking_eligible,
            trust_reason=trust_reason,
            cluster_id=cluster_id,
            vote_metadata={
                "created_at": datetime.now(timezone.utc).isoformat(),
                "source_attempt_id": source_attempt_id,
                "reviewer_network_hash": request_network_hash,
                "reviewer_registration_network_hash": reviewer_registration_network,
                "provenance": "observed_subtask_outcome" if trusted_outcome else "direct_vote",
            },
        )
        if result["status"] == "target_missing":
            raise HTTPException(status_code=404, detail=f"{target_type.title()} not found")
        if result["status"] == "no_vote":
            raise HTTPException(status_code=400, detail="No vote to remove")
        if result["status"] == "already_same":
            raise HTTPException(status_code=409, detail=f"Already voted {new_vote.value}")
        return VoteResponse(
            vote=result["vote"],
            upvote_count=result["upvote_count"],
            downvote_count=result["downvote_count"],
            score=result["score"],
            trusted=result["trusted"],
            trust_reason=result["trust_reason"],
        )

    # Check for existing vote
    existing_vote = None
    try:
        existing_doc = await es.get(index="votes", id=vote_doc_id)
        existing_vote = existing_doc["_source"]["vote_type"]
    except Exception:
        pass

    # Calculate deltas for the denormalized counters
    upvote_delta = 0
    downvote_delta = 0

    if new_vote == VoteType.none:
        # Removing a vote
        if existing_vote is None:
            raise HTTPException(status_code=400, detail="No vote to remove")
        # Delete the vote document
        await es.delete(index="votes", id=vote_doc_id, refresh="wait_for")
        if existing_vote == "up":
            upvote_delta = -1
        else:
            downvote_delta = -1

    elif existing_vote is None:
        # New vote (no previous vote exists)
        vote_doc = {
            "target_id": target_id,
            "target_type": target_type,
            "user_id": user["id"],
            "vote_type": new_vote.value,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await es.index(
            index="votes",
            id=vote_doc_id,
            document=vote_doc,
            refresh="wait_for",
        )
        if new_vote == VoteType.up:
            upvote_delta = 1
        else:
            downvote_delta = 1

    elif existing_vote == new_vote.value:
        # Already voted the same way
        raise HTTPException(status_code=409, detail=f"Already voted {new_vote.value}")

    else:
        # Changing vote direction (up → down or down → up)
        await es.update(
            index="votes",
            id=vote_doc_id,
            doc={"vote_type": new_vote.value},
            refresh="wait_for",
        )
        if new_vote == VoteType.up:
            upvote_delta = 1
            downvote_delta = -1
        else:
            upvote_delta = -1
            downvote_delta = 1

    # Atomic counter update on the target document via Painless script
    await es.update(
        index=target_index,
        id=target_id,
        script={
            "source": """
                ctx._source.upvote_count += params.up_delta;
                ctx._source.downvote_count += params.down_delta;
                ctx._source.score = ctx._source.upvote_count - ctx._source.downvote_count;
            """,
            "params": {
                "up_delta": upvote_delta,
                "down_delta": downvote_delta,
            },
        },
        refresh="wait_for",
    )

    # Fetch updated counts to return
    updated = await es.get(index=target_index, id=target_id)
    src = updated["_source"]

    return VoteResponse(
        vote=new_vote.value,
        upvote_count=src["upvote_count"],
        downvote_count=src["downvote_count"],
        score=src["score"],
        trusted=ranking_eligible,
        trust_reason=trust_reason,
    )


# ──────────────────────────────────────────────────────────────
# POST /questions/{question_id}/vote  — Vote on a question
# ──────────────────────────────────────────────────────────────


@router.post("/questions/{question_id}/vote", response_model=VoteResponse)
async def vote_on_question(
    question_id: str,
    body: VoteRequest,
    request: Request,
    access_token: str | None = Query(None),
    user: dict = Depends(get_current_user),
):
    """Upvote, downvote, or remove vote on a question. Requires authentication."""
    if memory_reads_protected():
        raise HTTPException(status_code=403, detail="Protected votes require a completed subtask outcome")
    return await _cast_vote(
        target_id=question_id,
        target_type="question",
        target_index="questions",
        vote_req=body,
        user=user,
        access_token=access_token,
        request_network_hash=client_network_key(request),
    )


# ──────────────────────────────────────────────────────────────
# POST /answers/{answer_id}/vote  — Vote on an answer
# ──────────────────────────────────────────────────────────────


@router.post("/answers/{answer_id}/vote", response_model=VoteResponse)
async def vote_on_answer(
    answer_id: str,
    body: VoteRequest,
    request: Request,
    access_token: str | None = Query(None),
    user: dict = Depends(get_current_user),
):
    """Upvote, downvote, or remove vote on an answer. Requires authentication."""
    if memory_reads_protected():
        raise HTTPException(status_code=403, detail="Protected votes require a completed subtask outcome")
    return await _cast_vote(
        target_id=answer_id,
        target_type="answer",
        target_index="answers",
        vote_req=body,
        user=user,
        access_token=access_token,
        request_network_hash=client_network_key(request),
    )
