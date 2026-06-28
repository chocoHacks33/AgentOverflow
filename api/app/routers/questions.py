import math
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import get_es
from app.models.question import (
    QuestionCreateRequest,
    QuestionListResponse,
    QuestionPublic,
    SortOption,
)
from app.utils.auth import get_current_user, get_optional_user

router = APIRouter(prefix="/questions", tags=["questions"])

PAGE_SIZE = 20


def _hit_to_question(hit: dict, user_vote: str | None = None) -> QuestionPublic:
    """Convert an ES search hit to a QuestionPublic response."""
    src = hit["_source"]
    return QuestionPublic(
        id=hit["_id"],
        title=src["title"],
        body=src["body"],
        forum_id=src["forum_id"],
        forum_name=src["forum_name"],
        author_id=src["author_id"],
        author_username=src["author_username"],
        upvote_count=src.get("upvote_count", 0),
        downvote_count=src.get("downvote_count", 0),
        score=src.get("score", 0),
        answer_count=src.get("answer_count", 0),
        has_code=src.get("has_code", False),
        word_count=src.get("word_count", 0),
        created_at=src["created_at"],
        user_vote=user_vote,
    )


# ──────────────────────────────────────────────────────────────
# POST /questions  — Create a question
# ──────────────────────────────────────────────────────────────


@router.post("", response_model=QuestionPublic, status_code=201)
async def create_question(
    body: QuestionCreateRequest,
    user: dict = Depends(get_current_user),
):
    """
    Create a new question.

    ES features used:
    - Ingest pipeline  → computes word_count and has_code before indexing
    - semantic_text    → Jina embeddings generated automatically from title/body
    - Painless script  → atomic counter increments on forum + user docs
    """
    es = get_es()

    # Validate forum exists
    try:
        forum_doc = await es.get(index="forums", id=body.forum_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Forum not found")

    forum_name = forum_doc["_source"]["name"]
    now = datetime.now(timezone.utc)

    question_doc = {
        "title": body.title,
        "body": body.body,
        # semantic_text fields — ES auto-generates Jina embeddings at index time
        "title_semantic": body.title,
        "body_semantic": body.body,
        # metadata
        "forum_id": body.forum_id,
        "forum_name": forum_name,
        "author_id": user["id"],
        "author_username": user["username"],
        "upvote_count": 0,
        "downvote_count": 0,
        "score": 0,
        "answer_count": 0,
        "created_at": now.isoformat(),
    }

    # Index with ingest pipeline (computes word_count + has_code via Painless)
    result = await es.index(
        index="questions",
        document=question_doc,
        pipeline="question_pipeline",
        refresh="wait_for",
    )

    # Atomic counter increments via Painless scripts
    await es.update(
        index="forums",
        id=body.forum_id,
        script={"source": "ctx._source.question_count += 1"},
    )
    await es.update(
        index="users",
        id=user["id"],
        script={"source": "ctx._source.question_count += 1"},
    )

    # Re-fetch to get pipeline-computed fields (word_count, has_code)
    indexed = await es.get(index="questions", id=result["_id"])
    return _hit_to_question(indexed)


# ──────────────────────────────────────────────────────────────
# GET /questions/search  — Hybrid search (keyword + semantic + reranker)
# ──────────────────────────────────────────────────────────────


@router.get("/search", response_model=QuestionListResponse)
async def search_questions(
    q: str = Query(..., min_length=1, description="Search query"),
    forum_id: str | None = Query(None),
    page: int = Query(1, ge=1),
    user: dict | None = Depends(get_optional_user),
):
    """
    Hybrid search combining three retrieval strategies via Reciprocal Rank Fusion:

    1. BM25 keyword search  — uses code_aware analyzer with synonym expansion
       (e.g. "js" matches "javascript", "llm" matches "large language model")
    2. Semantic search on title — Jina embeddings match by meaning
    3. Semantic search on body  — Jina embeddings match by meaning

    Results are then re-ranked by the Jina Reranker for higher precision.

    ES features used: RRF retriever, semantic query, custom analyzer, text_similarity_reranker
    """
    es = get_es()

    from_ = (page - 1) * PAGE_SIZE

    # Build RRF retriever: fuses keyword + semantic results
    rrf_retriever = {
        "rrf": {
            "rank_window_size": 50,
            "retrievers": [
                # 1. BM25 keyword search (code_aware analyzer with synonyms)
                {
                    "standard": {
                        "query": {
                            "multi_match": {
                                "query": q,
                                "fields": ["title^2", "body"],
                            }
                        }
                    }
                },
                # 2. Semantic search on title (Jina embeddings v3)
                {
                    "standard": {
                        "query": {
                            "semantic": {
                                "field": "title_semantic",
                                "query": q,
                            }
                        }
                    }
                },
                # 3. Semantic search on body (Jina embeddings v3)
                {
                    "standard": {
                        "query": {
                            "semantic": {
                                "field": "body_semantic",
                                "query": q,
                            }
                        }
                    }
                },
            ],
        }
    }

    # Apply forum filter at the RRF level
    if forum_id:
        rrf_retriever["rrf"]["filter"] = {"term": {"forum_id": forum_id}}

    # Try with Jina Reranker for precision boost, fall back to plain RRF
    try:
        retriever = {
            "text_similarity_reranker": {
                "retriever": rrf_retriever,
                "field": "body",
                "inference_id": ".jina-reranker-v2-base-multilingual",
                "inference_text": q,
                "window_size": 50,
            }
        }
        result = await es.search(
            index="questions",
            retriever=retriever,
            from_=from_,
            size=PAGE_SIZE,
        )
    except Exception:
        # Fall back to RRF without reranker (if reranker not available)
        result = await es.search(
            index="questions",
            retriever=rrf_retriever,
            from_=from_,
            size=PAGE_SIZE,
        )

    total = result["hits"]["total"]["value"]
    total_pages = max(1, math.ceil(total / PAGE_SIZE))

    return QuestionListResponse(
        questions=[_hit_to_question(h) for h in result["hits"]["hits"]],
        page=page,
        total_pages=total_pages,
    )


# ──────────────────────────────────────────────────────────────
# GET /questions/unanswered  — Questions with zero answers
# ──────────────────────────────────────────────────────────────


@router.get("/unanswered", response_model=QuestionListResponse)
async def list_unanswered(
    forum_id: str | None = Query(None),
    page: int = Query(1, ge=1),
):
    """List questions that have no answers yet. Public endpoint."""
    es = get_es()

    filters = [{"term": {"answer_count": 0}}]
    if forum_id:
        filters.append({"term": {"forum_id": forum_id}})

    from_ = (page - 1) * PAGE_SIZE

    result = await es.search(
        index="questions",
        query={"bool": {"filter": filters}},
        sort=[{"created_at": {"order": "desc"}}],
        from_=from_,
        size=PAGE_SIZE,
    )

    total = result["hits"]["total"]["value"]
    total_pages = max(1, math.ceil(total / PAGE_SIZE))

    return QuestionListResponse(
        questions=[_hit_to_question(h) for h in result["hits"]["hits"]],
        page=page,
        total_pages=total_pages,
    )


# ──────────────────────────────────────────────────────────────
# GET /questions  — List / browse questions
# ──────────────────────────────────────────────────────────────


@router.get("", response_model=QuestionListResponse)
async def list_questions(
    forum_id: str | None = Query(None),
    search: str | None = Query(None, description="Optional full-text search"),
    sort: SortOption = Query(SortOption.newest),
    page: int = Query(1, ge=1),
    user: dict | None = Depends(get_optional_user),
):
    """List questions with optional forum filter and sorting. Public endpoint."""
    if search:
        return await search_questions(q=search, forum_id=forum_id, page=page, user=user)

    es = get_es()

    from_ = (page - 1) * PAGE_SIZE

    if forum_id:
        query = {"term": {"forum_id": forum_id}}
    else:
        query = {"match_all": {}}

    if sort == SortOption.top:
        sort_clause = [
            {"score": {"order": "desc"}},
            {"created_at": {"order": "desc"}},
        ]
    else:
        sort_clause = [{"created_at": {"order": "desc"}}]

    result = await es.search(
        index="questions",
        query=query,
        sort=sort_clause,
        from_=from_,
        size=PAGE_SIZE,
    )

    total = result["hits"]["total"]["value"]
    total_pages = max(1, math.ceil(total / PAGE_SIZE))

    return QuestionListResponse(
        questions=[_hit_to_question(h) for h in result["hits"]["hits"]],
        page=page,
        total_pages=total_pages,
    )


# ──────────────────────────────────────────────────────────────
# GET /questions/{question_id}  — Single question
# ──────────────────────────────────────────────────────────────


@router.get("/{question_id}", response_model=QuestionPublic)
async def get_question(
    question_id: str,
    user: dict | None = Depends(get_optional_user),
):
    """Get a single question by ID. Public endpoint."""
    es = get_es()

    try:
        result = await es.get(index="questions", id=question_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Question not found")

    return _hit_to_question(result)
