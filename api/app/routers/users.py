import math

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import get_es
from app.models.answer import AnswerListResponse, AnswerPublic
from app.models.question import QuestionListResponse, QuestionPublic, SortOption
from app.models.user import UserPublic
from app.utils.auth import get_current_user

router = APIRouter(prefix="/users", tags=["users"])

PAGE_SIZE = 20


# ──────────────────────────────────────────────────────────────
# GET /users/me  — Current authenticated user
# ──────────────────────────────────────────────────────────────


@router.get("/me", response_model=UserPublic)
async def get_me(user: dict = Depends(get_current_user)):
    """Get the currently authenticated user's profile."""
    return UserPublic(
        id=user["id"],
        username=user["username"],
        question_count=user.get("question_count", 0),
        answer_count=user.get("answer_count", 0),
        reputation=user.get("reputation", 0),
        created_at=user["created_at"],
    )


# ──────────────────────────────────────────────────────────────
# GET /users/top  — Leaderboard
# ──────────────────────────────────────────────────────────────


@router.get("/top", response_model=list[UserPublic])
async def get_top_users(
    limit: int = Query(10, ge=1, le=50),
):
    """Get top users by reputation. Public endpoint."""
    es = get_es()

    result = await es.search(
        index="users",
        query={"match_all": {}},
        sort=[
            {"reputation": {"order": "desc"}},
            {"question_count": {"order": "desc"}},
        ],
        size=limit,
    )

    return [
        UserPublic(id=hit["_id"], **hit["_source"])
        for hit in result["hits"]["hits"]
    ]


# ──────────────────────────────────────────────────────────────
# GET /users/username/{username}  — User by username
# ──────────────────────────────────────────────────────────────


@router.get("/username/{username}", response_model=UserPublic)
async def get_user_by_username(username: str):
    """Get a user profile by username. Public endpoint."""
    es = get_es()

    result = await es.search(
        index="users",
        query={"term": {"username": username}},
        size=1,
    )

    if result["hits"]["total"]["value"] == 0:
        raise HTTPException(status_code=404, detail="User not found")

    hit = result["hits"]["hits"][0]
    return UserPublic(id=hit["_id"], **hit["_source"])


# ──────────────────────────────────────────────────────────────
# GET /users/{user_id}  — User by ID
# ──────────────────────────────────────────────────────────────


@router.get("/{user_id}", response_model=UserPublic)
async def get_user(user_id: str):
    """Get a user profile by ID. Public endpoint."""
    es = get_es()

    try:
        result = await es.get(index="users", id=user_id)
    except Exception:
        raise HTTPException(status_code=404, detail="User not found")

    return UserPublic(id=result["_id"], **result["_source"])


# ──────────────────────────────────────────────────────────────
# GET /users/{user_id}/questions  — User's questions
# ──────────────────────────────────────────────────────────────


@router.get("/{user_id}/questions", response_model=QuestionListResponse)
async def get_user_questions(
    user_id: str,
    sort: SortOption = Query(SortOption.newest),
    page: int = Query(1, ge=1),
):
    """Get all questions by a user. Public endpoint."""
    es = get_es()

    from_ = (page - 1) * PAGE_SIZE

    if sort == SortOption.top:
        sort_clause = [
            {"score": {"order": "desc"}},
            {"created_at": {"order": "desc"}},
        ]
    else:
        sort_clause = [{"created_at": {"order": "desc"}}]

    result = await es.search(
        index="questions",
        query={"term": {"author_id": user_id}},
        sort=sort_clause,
        from_=from_,
        size=PAGE_SIZE,
    )

    total = result["hits"]["total"]["value"]
    total_pages = max(1, math.ceil(total / PAGE_SIZE))

    return QuestionListResponse(
        questions=[
            QuestionPublic(
                id=hit["_id"],
                title=hit["_source"]["title"],
                body=hit["_source"]["body"],
                forum_id=hit["_source"]["forum_id"],
                forum_name=hit["_source"]["forum_name"],
                author_id=hit["_source"]["author_id"],
                author_username=hit["_source"]["author_username"],
                upvote_count=hit["_source"].get("upvote_count", 0),
                downvote_count=hit["_source"].get("downvote_count", 0),
                score=hit["_source"].get("score", 0),
                answer_count=hit["_source"].get("answer_count", 0),
                has_code=hit["_source"].get("has_code", False),
                word_count=hit["_source"].get("word_count", 0),
                created_at=hit["_source"]["created_at"],
            )
            for hit in result["hits"]["hits"]
        ],
        page=page,
        total_pages=total_pages,
    )


# ──────────────────────────────────────────────────────────────
# GET /users/{user_id}/answers  — User's answers
# ──────────────────────────────────────────────────────────────


@router.get("/{user_id}/answers", response_model=AnswerListResponse)
async def get_user_answers(
    user_id: str,
    sort: SortOption = Query(SortOption.newest),
    page: int = Query(1, ge=1),
):
    """Get all answers by a user. Public endpoint."""
    es = get_es()

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
        query={"term": {"author_id": user_id}},
        sort=sort_clause,
        from_=from_,
        size=PAGE_SIZE,
    )

    total = result["hits"]["total"]["value"]
    total_pages = max(1, math.ceil(total / PAGE_SIZE))

    return AnswerListResponse(
        answers=[
            AnswerPublic(
                id=hit["_id"],
                body=hit["_source"]["body"],
                question_id=hit["_source"]["question_id"],
                author_id=hit["_source"]["author_id"],
                author_username=hit["_source"]["author_username"],
                upvote_count=hit["_source"].get("upvote_count", 0),
                downvote_count=hit["_source"].get("downvote_count", 0),
                score=hit["_source"].get("score", 0),
                created_at=hit["_source"]["created_at"],
            )
            for hit in result["hits"]["hits"]
        ],
        page=page,
        total_pages=total_pages,
    )
