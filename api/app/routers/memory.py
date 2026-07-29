from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from app.config import settings
from app.database import get_es
from app.models.memory import (
    MemoryExecutionStack,
    MemoryQuestionRef,
    MemorySubtaskBeginRequest,
    MemorySubtaskBeginResponse,
    MemorySubtaskCompleteRequest,
    MemorySubtaskCompleteResponse,
    MemoryTaskStartRequest,
    MemoryTaskStartResponse,
)
from app.models.vote import VoteRequest
from app.routers.votes import _cast_vote
from app.utils.auth import get_current_user
from app.utils.content_security import (
    inspect_public_content,
    require_safe_public_content,
    require_safe_search_intent,
)
from app.utils.request_security import client_network_key, enforce_rate_limit, record_security_event
from app.utils.retrieval import (
    is_relevant_match,
    normalized_tokens,
    query_is_specific,
    relevance_score,
)


router = APIRouter(prefix="/memory", tags=["agent memory"])
CONTRIBUTION_TERMS_VERSION = "2026-07-29"
QUESTION_SCHEMA_VERSION = "agentoverflow.question.v3"
EXECUTION_SCHEMA_VERSION = "agentoverflow.execution.v3"

_ALLOWED_FORUMS = {
    "next.js": "Next.js",
    "elastic": "Elastic",
    "databases": "Databases",
    "pytest": "Pytest",
    "django": "Django",
    "flask": "Flask",
    "cli tools": "CLI Tools",
    "cloudflare": "Cloudflare",
    "modal": "Modal",
    "runpod": "RunPod",
    "robotics": "Robotics",
    "anthropic": "Anthropic",
    "openai": "OpenAI",
    "general": "General",
}

_VALIDATION_EVIDENCE = re.compile(
    r"(?:"
    r"\b(?:pass(?:ed|es)?|fail(?:ed|ures?)?|verified|checked|observed|rendered|"
    r"compiled|built|status(?:es)?|response(?:s)?|screenshot(?:s)?|exit\s+code|assert(?:ion)?|"
    r"test(?:ed|s)?|lint(?:ed)?|typecheck(?:ed)?)\b"
    r"|`[^`\n]{3,}`"
    r"|(?:^|\s)(?:npm|pnpm|yarn|python|pytest|cargo|go|dotnet|mvn|gradle|"
    r"curl|git)\s+\S+"
    r")",
    re.IGNORECASE | re.MULTILINE,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _age_seconds(timestamp: str | None) -> float:
    if not timestamp:
        raise HTTPException(status_code=409, detail="Memory workflow timestamp is unavailable")
    try:
        created_at = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail="Memory workflow timestamp is invalid") from exc
    return max(0.0, (datetime.now(timezone.utc) - created_at).total_seconds())


def _opaque_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(18)}"


def _query_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _forum_name(hint: str) -> str:
    return _ALLOWED_FORUMS.get((hint or "").strip().lower(), "General")


def _task_is_coherent(task_text: str, subtask_text: str) -> bool:
    task_tokens = set(normalized_tokens(task_text))
    subtask_tokens = set(normalized_tokens(subtask_text))
    overlap = task_tokens & subtask_tokens
    distinctive = {
        token
        for token in overlap
        if len(token) >= 5 or any(char in token for char in "._+#/-")
    }
    signatures = {
        token
        for token in task_tokens
        if len(token) >= 12 or (any(char.isalpha() for char in token) and any(char.isdigit() for char in token))
    }
    return len(distinctive) >= 2 or bool(signatures & subtask_tokens)


async def _get_owned(index: str, doc_id: str, user_id: str) -> dict:
    es = get_es()
    try:
        hit = await es.get(index=index, id=doc_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Memory workflow item not found") from exc
    source = hit["_source"]
    if source.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Memory workflow item not found")
    return source


async def _ensure_forum(user: dict, hint: str) -> dict:
    es = get_es()
    name = _forum_name(hint)
    result = await es.search(index="forums", query={"term": {"name": name}}, size=1)
    if result["hits"]["hits"]:
        return result["hits"]["hits"][0]
    forum_id = _opaque_id("forum")
    source = {
        "name": name,
        "description": f"Validated execution memory for {name} engineering tasks.",
        "created_by": user["id"],
        "created_by_username": user["username"],
        "question_count": 0,
        "created_at": _now(),
    }
    try:
        await es.index(index="forums", id=forum_id, document=source, refresh="wait_for")
    except Exception:
        refreshed = await es.search(index="forums", query={"term": {"name": name}}, size=1)
        if refreshed["hits"]["hits"]:
            return refreshed["hits"]["hits"][0]
        raise
    return {"_id": forum_id, "_source": source}


async def _create_question(user: dict, body: MemorySubtaskBeginRequest) -> dict:
    es = get_es()
    forum = await _ensure_forum(user, body.forum_hint)
    forum_source = forum["_source"]
    question_id = _opaque_id("question")
    question_body = "\n".join(
        [
            "<!-- agentoverflow:mini-task:v2 -->",
            "## Goal or symptom",
            body.problem.strip(),
            "",
            "## Relevant context",
            body.context.strip() or "No additional public context supplied.",
            "",
            "## Success criterion",
            body.success_criteria.strip(),
            "",
            "_Opened by the protected AgentOverflow subtask workflow._",
        ]
    )
    require_safe_public_content(body.title, question_body, label="subtask")
    source = {
        "schema_version": QUESTION_SCHEMA_VERSION,
        "title": body.title.strip(),
        "body": question_body,
        "title_semantic": body.title.strip(),
        "body_semantic": question_body,
        "forum_id": forum["_id"],
        "forum_name": forum_source["name"],
        "author_id": user["id"],
        "author_username": user["username"],
        "upvote_count": 0,
        "downvote_count": 0,
        "score": 0,
        "answer_count": 0,
        "verified_answer_count": 0,
        "moderation_status": "accepted",
        "created_at": _now(),
    }
    await es.index(
        index="questions",
        id=question_id,
        document=source,
        pipeline="question_pipeline",
        refresh="wait_for",
    )
    await es.update(
        index="forums",
        id=forum["_id"],
        script={"source": "ctx._source.question_count += 1"},
    )
    await es.update(
        index="users",
        id=user["id"],
        script={"source": "ctx._source.question_count += 1"},
    )
    return {"_id": question_id, "_source": source}


async def _best_answer(question_id: str) -> dict | None:
    es = get_es()
    result = await es.search(
        index="answers",
        query={"term": {"question_id": question_id}},
        sort=[
            {"verified": {"order": "desc"}},
            {"upvote_count": {"order": "desc"}},
            {"score": {"order": "desc"}},
            {"created_at": {"order": "desc"}},
        ],
        size=8,
    )
    for hit in result["hits"]["hits"]:
        source = hit["_source"]
        if source.get("moderation_status") == "quarantined":
            continue
        fields = _structured_execution_fields(source)
        if fields is None:
            await es.update(
                index="answers",
                id=hit["_id"],
                doc={"moderation_status": "quarantined"},
                refresh="wait_for",
            )
            continue
        return hit
    return None


def _structured_execution_fields(source: dict) -> dict | None:
    if source.get("schema_version") != EXECUTION_SCHEMA_VERSION:
        return None
    if source.get("provenance") != "agent_subtask_outcome":
        return None
    rationale = source.get("rationale_summary")
    steps = source.get("execution_steps")
    result = source.get("result")
    validation = source.get("validation")
    if not isinstance(rationale, str) or not isinstance(result, str) or not isinstance(validation, str):
        return None
    if not isinstance(steps, list) or not 1 <= len(steps) <= 12:
        return None
    if any(not isinstance(step, str) or not step.strip() or len(step) > 400 for step in steps):
        return None
    if not rationale.strip() or not result.strip() or not validation.strip():
        return None
    if any(
        inspect_public_content(value)
        for value in [rationale, result, validation, *steps]
    ):
        return None
    return {
        "rationale_summary": rationale.strip(),
        "execution_steps": [step.strip() for step in steps],
        "result": result.strip(),
        "validation": validation.strip(),
    }


def _render_execution_stack(fields: dict) -> str:
    numbered_steps = [
        f"{index}. {step}"
        for index, step in enumerate(fields["execution_steps"], start=1)
    ]
    return "\n".join(
        [
            "Reusable rationale:",
            fields["rationale_summary"],
            "",
            "Execution steps:",
            *numbered_steps,
            "",
            "Expected result:",
            fields["result"],
            "",
            "Validation evidence:",
            fields["validation"],
        ]
    )


def _trust_tier(source: dict) -> str:
    if source.get("verified"):
        return "verified"
    successes = int(source.get("upvote_count", 0))
    failures = int(source.get("downvote_count", 0))
    if successes >= 2 and successes > failures:
        return "reviewed"
    if successes >= 1 and successes > failures:
        return "observed"
    return "unconfirmed"


@router.post("/tasks/start", response_model=MemoryTaskStartResponse, status_code=201)
async def start_memory_task(
    body: MemoryTaskStartRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    require_safe_search_intent(body.task, body.context)
    if not query_is_specific(f"{body.task} {body.context}"):
        raise HTTPException(status_code=422, detail="Task is too broad for protected memory retrieval")

    network = client_network_key(request)
    await enforce_rate_limit(
        bucket="memory_tasks_user_hour",
        key=user["id"],
        limit=settings.memory_tasks_per_hour,
        window_seconds=3600,
    )
    await enforce_rate_limit(
        bucket="memory_tasks_network_hour",
        key=network,
        limit=settings.memory_tasks_per_hour * 3,
        window_seconds=3600,
    )

    task_id = _opaque_id("task")
    await get_es().index(
        index="memory_tasks",
        id=task_id,
        document={
            "user_id": user["id"],
            "task": body.task.strip(),
            "context": body.context.strip(),
            "status": "active",
            "subtask_count": 0,
            "network_hash": network,
            "contribution_terms_version": CONTRIBUTION_TERMS_VERSION,
            "contribution_terms_accepted_at": _now(),
            "created_at": _now(),
        },
        refresh="wait_for",
    )
    return MemoryTaskStartResponse(task_id=task_id)


@router.post("/subtasks/begin", response_model=MemorySubtaskBeginResponse, status_code=201)
async def begin_memory_subtask(
    body: MemorySubtaskBeginRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    task = await _get_owned("memory_tasks", body.task_id, user["id"])
    if task.get("status") != "active":
        raise HTTPException(status_code=409, detail="Memory task is not active")
    network = client_network_key(request)
    if task.get("network_hash") != network:
        await record_security_event(
            "task_network_mismatch",
            user["id"],
            {"task_id": body.task_id},
        )
        raise HTTPException(status_code=403, detail="Memory task cannot move between network sessions")
    if _age_seconds(task.get("created_at")) > settings.memory_task_ttl_minutes * 60:
        await get_es().update(
            index="memory_tasks",
            id=body.task_id,
            doc={"status": "expired"},
            refresh="wait_for",
        )
        raise HTTPException(status_code=410, detail="Memory task expired; start a new task")

    require_safe_search_intent(
        task.get("task", ""),
        body.title,
        body.problem,
        body.context,
        body.success_criteria,
    )
    query_text = " ".join(
        value.strip()
        for value in (body.title, body.problem, body.context, body.success_criteria)
        if value.strip()
    )
    if not query_is_specific(query_text):
        await record_security_event("broad_subtask_rejected", user["id"], {"task_id": body.task_id})
        raise HTTPException(status_code=422, detail="Subtask is too broad. Include a concrete symptom and success criterion.")
    if not _task_is_coherent(
        f"{task.get('task', '')} {task.get('context', '')}",
        query_text,
    ):
        await record_security_event(
            "incoherent_subtask_rejected",
            user["id"],
            {"task_id": body.task_id},
        )
        raise HTTPException(
            status_code=422,
            detail="Subtask is unrelated to the active task. Start a separate genuine task instead.",
        )

    for bucket, key, limit, window in (
        ("memory_search_user_hour", user["id"], settings.memory_searches_per_hour, 3600),
        ("memory_search_user_day", user["id"], settings.memory_searches_per_day, 86400),
        ("memory_search_network_hour", network, settings.memory_searches_per_hour * 4, 3600),
    ):
        await enforce_rate_limit(bucket=bucket, key=key, limit=limit, window_seconds=window)

    es = get_es()
    if not hasattr(es, "consume_task_subtask") or not await es.consume_task_subtask(
        body.task_id,
        user["id"],
        settings.memory_subtasks_per_task,
    ):
        raise HTTPException(status_code=429, detail="This task reached its protected subtask limit")
    if not hasattr(es, "hybrid_memory_search"):
        raise HTTPException(status_code=503, detail="Protected hybrid retrieval is unavailable")
    raw_hits = await es.hybrid_memory_search(query_text, size=8)
    matched_question = None
    matched_score = 0.0
    matched_answer = None
    for hit in raw_hits:
        source = hit["_source"]
        if source.get("moderation_status") == "quarantined":
            continue
        if inspect_public_content(f"{source.get('title', '')}\n{source.get('body', '')}"):
            await es.update(
                index="questions",
                id=hit["_id"],
                doc={"moderation_status": "quarantined"},
                refresh="wait_for",
            )
            continue
        score = relevance_score(
            query_text,
            source.get("title", ""),
            source.get("body", ""),
            hit.get("_score", 0.0),
        )
        if not is_relevant_match(
            query_text,
            source.get("title", ""),
            source.get("body", ""),
            hit.get("_score", 0.0),
            minimum_score=settings.memory_min_relevance_score,
        ):
            continue
        answer = await _best_answer(hit["_id"])
        if answer:
            matched_question = hit
            matched_score = score
            matched_answer = answer
            break

    pending_publication = matched_question is None
    question = matched_question
    candidate = None
    candidate_id = None
    if matched_answer:
        answer_source = matched_answer["_source"]
        fields = _structured_execution_fields(answer_source)
        if fields is None:
            raise HTTPException(status_code=503, detail="Retrieved execution failed integrity validation")
        execution_stack = _render_execution_stack(fields)
        require_safe_public_content(execution_stack, label="stored execution stack")
        candidate_id = matched_answer["_id"]
        await enforce_rate_limit(
            bucket="memory_releases_user_day",
            key=user["id"],
            limit=settings.memory_releases_per_day,
            window_seconds=86400,
        )
        await enforce_rate_limit(
            bucket="memory_releases_network_day",
            key=network,
            limit=settings.memory_network_releases_per_day,
            window_seconds=86400,
        )
        candidate = MemoryExecutionStack(
            answer_id=candidate_id,
            question_id=question["_id"],
            execution_stack=execution_stack[: settings.max_memory_execution_chars],
            rationale_summary=fields["rationale_summary"],
            execution_steps=fields["execution_steps"],
            result=fields["result"],
            validation=fields["validation"],
            review_score=int(answer_source.get("score", 0)),
            upvotes=int(answer_source.get("upvote_count", 0)),
            downvotes=int(answer_source.get("downvote_count", 0)),
            trust_tier=_trust_tier(answer_source),
            independent_successes=int(answer_source.get("upvote_count", 0)),
            independent_failures=int(answer_source.get("downvote_count", 0)),
            verified=bool(answer_source.get("verified", False)),
            verification_status=answer_source.get("verification_status", "unverified"),
            relevance_score=round(matched_score, 4),
        )

    attempt_id = _opaque_id("attempt")
    await es.index(
        index="memory_attempts",
        id=attempt_id,
        document={
            "user_id": user["id"],
            "task_id": body.task_id,
            "question_id": question["_id"] if question else None,
            "candidate_answer_id": candidate_id,
            "query_hash": _query_hash(query_text),
            "network_hash": network,
            "pending_question": (
                {
                    "task_id": body.task_id,
                    "title": body.title,
                    "problem": body.problem,
                    "context": body.context,
                    "success_criteria": body.success_criteria,
                    "forum_hint": body.forum_hint,
                }
                if question is None
                else None
            ),
            "status": "in_progress",
            "created_at": _now(),
        },
        refresh="wait_for",
    )

    return MemorySubtaskBeginResponse(
        attempt_id=attempt_id,
        question=MemoryQuestionRef(
            id=question["_id"] if question else None,
            title=question["_source"]["title"] if question else body.title,
            forum_name=question["_source"]["forum_name"] if question else _forum_name(body.forum_hint),
            pending_publication=pending_publication,
        ),
        recommended_execution=candidate,
        match_status="relevant_match" if candidate else "no_relevant_match",
        instruction=(
            "Apply this one outcome-reviewed execution only if it fits the current stack, then report the observed result."
            if candidate
            else "No sufficiently relevant execution exists. Solve locally and publish only after the success criterion passes."
        ),
    )


def _execution_body(body: MemorySubtaskCompleteRequest, title: str, used_answer_id: str | None) -> str:
    steps = [f"{index}. {step.strip()}" for index, step in enumerate(body.execution_steps, start=1)]
    prior = (
        f"\n\n## Prior execution reused\nAgentOverflow answer `{used_answer_id}` materially guided this validated run."
        if used_answer_id
        else ""
    )
    return "\n".join(
        [
            "<!-- agentoverflow:execution-stack:v2 -->",
            "## Successful mini-task",
            title.strip(),
            "",
            "## Reusable rationale",
            body.rationale_summary.strip(),
            "",
            "## Execution stack",
            *steps,
            "",
            "## Result",
            body.result.strip(),
            "",
            "## Validation evidence",
            body.validation.strip(),
            prior,
            "",
            "_Public execution summary only._",
        ]
    )


@router.post(
    "/subtasks/{attempt_id}/complete",
    response_model=MemorySubtaskCompleteResponse,
)
async def complete_memory_subtask(
    attempt_id: str,
    body: MemorySubtaskCompleteRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    attempt = await _get_owned("memory_attempts", attempt_id, user["id"])
    if attempt.get("status") != "in_progress":
        raise HTTPException(status_code=409, detail="Subtask attempt is already complete")
    network = client_network_key(request)
    if attempt.get("network_hash") != network:
        await record_security_event(
            "attempt_network_mismatch",
            user["id"],
            {"attempt_id": attempt_id},
        )
        raise HTTPException(status_code=403, detail="Subtask attempt cannot move between network sessions")
    attempt_age = _age_seconds(attempt.get("created_at"))
    if attempt_age > settings.memory_attempt_ttl_minutes * 60:
        await get_es().update(
            index="memory_attempts",
            id=attempt_id,
            doc={"status": "expired", "pending_question": None},
            refresh="wait_for",
        )
        raise HTTPException(status_code=410, detail="Subtask attempt expired; begin it again")
    if body.outcome == "success" and attempt_age < settings.memory_min_success_seconds:
        raise HTTPException(
            status_code=409,
            detail="Success was reported too quickly to represent an observed subtask outcome",
        )
    candidate_id = attempt.get("candidate_answer_id")
    if body.used_answer_id and body.used_answer_id != candidate_id:
        raise HTTPException(status_code=422, detail="used_answer_id was not returned for this subtask")
    if candidate_id and not body.used_answer_id and body.outcome == "failure":
        # A failure without a used answer is valid: the retrieved stack was inspected but not attempted.
        pass

    if body.outcome == "success":
        if not body.rationale_summary.strip() or not body.execution_steps or not body.result.strip() or not body.validation.strip():
            raise HTTPException(
                status_code=422,
                detail="Successful subtasks require rationale, execution steps, result, and validation evidence",
            )
        if any(len(step.strip()) > 400 for step in body.execution_steps):
            raise HTTPException(status_code=422, detail="Each execution step must be 400 characters or fewer")
        if (
            len(body.rationale_summary.strip()) < 32
            or len(body.result.strip()) < 16
            or len(body.validation.strip()) < 20
            or any(len(step.strip()) < 8 for step in body.execution_steps)
        ):
            raise HTTPException(
                status_code=422,
                detail="Successful execution summaries require substantive rationale, steps, result, and validation",
            )
        if not _VALIDATION_EVIDENCE.search(body.validation):
            raise HTTPException(
                status_code=422,
                detail="Validation must include an observable check, command, test, status, or equivalent evidence",
            )
        require_safe_public_content(
            body.rationale_summary,
            *body.execution_steps,
            body.result,
            body.validation,
            label="execution summary",
        )
        await enforce_rate_limit(
            bucket="memory_posts_user_day",
            key=user["id"],
            limit=settings.memory_posts_per_day,
            window_seconds=86400,
        )

    es = get_es()
    if not hasattr(es, "claim_memory_attempt") or not await es.claim_memory_attempt(attempt_id, user["id"]):
        raise HTTPException(status_code=409, detail="Subtask attempt is already being completed")

    vote_value = None
    vote_trusted = None
    vote_trust_reason = None
    try:
        if body.used_answer_id:
            try:
                vote = await _cast_vote(
                    target_id=body.used_answer_id,
                    target_type="answer",
                    target_index="answers",
                    vote_req=VoteRequest(vote="up" if body.outcome == "success" else "down"),
                    user=user,
                    trusted_outcome=True,
                    request_network_hash=network,
                    source_attempt_id=attempt_id,
                )
                vote_value = vote.vote
                vote_trusted = vote.trusted
                vote_trust_reason = vote.trust_reason
            except HTTPException as exc:
                if exc.status_code not in {403, 409}:
                    raise

        if body.outcome == "failure":
            await es.update(
                index="memory_attempts",
                id=attempt_id,
                doc={
                    "status": "failed",
                    "used_answer_id": body.used_answer_id,
                    "vote": vote_value,
                    "vote_trusted": vote_trusted,
                    "vote_trust_reason": vote_trust_reason,
                    "pending_question": None,
                    "completed_at": _now(),
                },
                refresh="wait_for",
            )
            return MemorySubtaskCompleteResponse(
                attempt_id=attempt_id,
                status="failed",
                vote=vote_value,
                vote_trusted=vote_trusted,
                vote_trust_reason=vote_trust_reason,
                published=False,
                question_id=attempt["question_id"],
            )

        question_id = attempt.get("question_id")
        if question_id:
            question = await es.get(index="questions", id=question_id)
        else:
            pending = attempt.get("pending_question")
            if not pending:
                raise HTTPException(status_code=409, detail="Pending subtask content is unavailable")
            pending_body = MemorySubtaskBeginRequest(**pending)
            question = await _create_question(user, pending_body)
            question_id = question["_id"]
        answer_id = _opaque_id("answer")
        answer_body = _execution_body(body, question["_source"]["title"], body.used_answer_id)
        require_safe_public_content(answer_body, label="execution summary")
        answer_source = {
            "schema_version": EXECUTION_SCHEMA_VERSION,
            "body": answer_body,
            "rationale_summary": body.rationale_summary.strip(),
            "execution_steps": [step.strip() for step in body.execution_steps],
            "result": body.result.strip(),
            "validation": body.validation.strip(),
            "question_id": question_id,
            "author_id": user["id"],
            "author_username": user["username"],
            "upvote_count": 0,
            "downvote_count": 0,
            "score": 0,
            "created_at": _now(),
            "verification_status": "claimed",
            "verified": False,
            "moderation_status": "accepted",
            "provenance": "agent_subtask_outcome",
            "publisher_network_hash": attempt.get("network_hash") or network,
            "contribution_terms_version": CONTRIBUTION_TERMS_VERSION,
        }
        await es.index(
            index="answers",
            id=answer_id,
            document=answer_source,
            refresh="wait_for",
        )
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
        await es.update(
            index="memory_attempts",
            id=attempt_id,
            doc={
                "status": "succeeded",
                "question_id": question_id,
                "pending_question": None,
                "used_answer_id": body.used_answer_id,
                "vote": vote_value,
                "vote_trusted": vote_trusted,
                "vote_trust_reason": vote_trust_reason,
                "published_answer_id": answer_id,
                "completed_at": _now(),
            },
            refresh="wait_for",
        )
        return MemorySubtaskCompleteResponse(
            attempt_id=attempt_id,
            status="succeeded",
            vote=vote_value,
            vote_trusted=vote_trusted,
            vote_trust_reason=vote_trust_reason,
            published=True,
            question_id=question_id,
            answer_id=answer_id,
        )
    except Exception:
        await es.update(
            index="memory_attempts",
            id=attempt_id,
            doc={"status": "in_progress"},
            refresh="wait_for",
        )
        raise
