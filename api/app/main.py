from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import close_es, init_es
from app.routers import answers, auth, commerce, escalations, forums, memory, questions, users, votes

# --- Jina inference endpoint IDs (pre-configured on Elastic Cloud Serverless) ---

JINA_EMBEDDING_ID = ".jina-embeddings-v3"
JINA_RERANKER_ID = ".jina-reranker-v2-base-multilingual"

# --- Simple index definitions (no special settings) ---

SIMPLE_INDICES = {
    "users": {
        "mappings": {
            "properties": {
                "username": {"type": "keyword"},
                "question_count": {"type": "integer"},
                "answer_count": {"type": "integer"},
                "reputation": {"type": "integer"},
                "created_at": {"type": "date"},
            }
        }
    },
    "forums": {
        "mappings": {
            "properties": {
                "name": {"type": "keyword"},
                "description": {"type": "text"},
                "created_by": {"type": "keyword"},
                "created_by_username": {"type": "keyword"},
                "question_count": {"type": "integer"},
                "created_at": {"type": "date"},
            }
        }
    },
    "answers": {
        "mappings": {
            "properties": {
                "body": {"type": "text"},
                "question_id": {"type": "keyword"},
                "author_id": {"type": "keyword"},
                "author_username": {"type": "keyword"},
                "upvote_count": {"type": "integer"},
                "downvote_count": {"type": "integer"},
                "score": {"type": "integer"},
                "created_at": {"type": "date"},
                "verification_status": {"type": "keyword"},
                "verified": {"type": "boolean"},
                "verification_engine": {"type": "keyword"},
                "verification_output": {"type": "text", "index": False},
                "verification_error": {"type": "text", "index": False},
                "verification_exit_code": {"type": "integer"},
                "verification_seconds": {"type": "float"},
                "verified_at": {"type": "date"},
            }
        }
    },
    "votes": {
        "mappings": {
            "properties": {
                "target_id": {"type": "keyword"},
                "target_type": {"type": "keyword"},
                "user_id": {"type": "keyword"},
                "vote_type": {"type": "keyword"},
                "created_at": {"type": "date"},
            }
        }
    },
    "escalations": {
        "mappings": {
            "properties": {
                "question_id": {"type": "keyword"},
                "question_title": {"type": "text"},
                "question_body": {"type": "text"},
                "forum_name": {"type": "keyword"},
                "requester_id": {"type": "keyword"},
                "requester_username": {"type": "keyword"},
                "reason": {"type": "text"},
                "repo": {"type": "keyword"},
                "backend": {"type": "keyword"},
                "status": {"type": "keyword"},
                "provider_message": {"type": "text"},
                "devin_session_id": {"type": "keyword"},
                "devin_session_url": {"type": "keyword"},
                "devin_status": {"type": "keyword"},
                "devin_error": {"type": "text", "index": False},
                "created_at": {"type": "date"},
                "updated_at": {"type": "date"},
            }
        }
    },
    "purchases": {
        "mappings": {
            "properties": {
                "answer_id": {"type": "keyword"},
                "question_id": {"type": "keyword"},
                "question_title": {"type": "text"},
                "buyer_id": {"type": "keyword"},
                "buyer_username": {"type": "keyword"},
                "status": {"type": "keyword"},
                "provider": {"type": "keyword"},
                "amount_cents": {"type": "integer"},
                "currency": {"type": "keyword"},
                "checkout_session_id": {"type": "keyword"},
                "checkout_url": {"type": "keyword"},
                "reasoning_time_reduction_pct": {"type": "integer"},
                "reasoning": {"type": "text"},
                "created_at": {"type": "date"},
                "updated_at": {"type": "date"},
                "paid_at": {"type": "date"},
            }
        }
    },
}

# --- Questions index (custom analyzer + semantic_text + ingest pipeline) ---

QUESTIONS_INDEX = {
    "settings": {
        "analysis": {
            "filter": {
                "code_synonyms": {
                    "type": "synonym",
                    "synonyms": [
                        "js, javascript",
                        "ts, typescript",
                        "py, python",
                        "llm, large language model",
                        "rag, retrieval augmented generation",
                        "ml, machine learning",
                        "ai, artificial intelligence",
                        "api, application programming interface",
                        "db, database",
                        "k8s, kubernetes",
                        "tf, tensorflow",
                        "np, numpy",
                        "pd, pandas",
                    ]
                }
            },
            "analyzer": {
                "code_aware": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase", "code_synonyms"],
                }
            },
        }
    },
    "mappings": {
        "properties": {
            # --- Text fields with custom code-aware analyzer ---
            "title": {
                "type": "text",
                "analyzer": "code_aware",
                "fields": {"keyword": {"type": "keyword"}},
            },
            "body": {
                "type": "text",
                "analyzer": "code_aware",
            },
            # --- Semantic fields (Jina embeddings via Elastic Inference Service) ---
            "title_semantic": {
                "type": "semantic_text",
                "inference_id": JINA_EMBEDDING_ID,
            },
            "body_semantic": {
                "type": "semantic_text",
                "inference_id": JINA_EMBEDDING_ID,
            },
            # --- Metadata fields ---
            "forum_id": {"type": "keyword"},
            "forum_name": {"type": "keyword"},
            "author_id": {"type": "keyword"},
            "author_username": {"type": "keyword"},
            "upvote_count": {"type": "integer"},
            "downvote_count": {"type": "integer"},
            "score": {"type": "integer"},
            "answer_count": {"type": "integer"},
            # --- Computed by ingest pipeline ---
            "has_code": {"type": "boolean"},
            "word_count": {"type": "integer"},
            "created_at": {"type": "date"},
        }
    },
}

# --- Ingest pipeline: computes derived fields before indexing ---

QUESTION_PIPELINE = {
    "description": "Pre-process questions: compute word count and detect code blocks",
    "processors": [
        {
            "script": {
                "source": """
                    ctx['word_count'] = ctx['body'].splitOnToken(' ').length;
                    ctx['has_code'] = ctx['body'].contains('```');
                """,
            }
        }
    ],
}


# --- App lifespan: init ES client + create indices at startup ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    backend = settings.storage_backend.lower().strip()
    registration_mode = settings.registration_mode.lower().strip()
    is_production = settings.vercel_env.lower().strip() == "production"
    if registration_mode not in {"open", "invite", "closed"}:
        raise RuntimeError("REGISTRATION_MODE must be open, invite, or closed")
    if is_production and settings.protected_memory_reads:
        if backend != "supabase" or settings.use_local_backend:
            raise RuntimeError(
                "Protected production must use Supabase and USE_LOCAL_BACKEND=false"
            )
        if not settings.supabase_database_url.strip():
            raise RuntimeError("SUPABASE_DATABASE_URL is required in protected production")
        if settings.max_memory_search_results != 1:
            raise RuntimeError("MAX_MEMORY_SEARCH_RESULTS must be 1 in protected production")
    if settings.protected_memory_reads and backend != "local":
        if len(settings.agentoverflow_access_secret.strip()) < 32:
            raise RuntimeError(
                "AGENTOVERFLOW_ACCESS_SECRET must be at least 32 characters in protected production"
            )
        if settings.supabase_auto_migrate:
            raise RuntimeError(
                "SUPABASE_AUTO_MIGRATE must be false in protected production"
            )
    if registration_mode == "invite" and len(settings.registration_invite_secret.strip()) < 32:
        raise RuntimeError(
            "REGISTRATION_INVITE_SECRET must be at least 32 characters in invite mode"
        )
    if settings.memory_task_ttl_minutes < 1 or settings.memory_attempt_ttl_minutes < 1:
        raise RuntimeError("Protected task and attempt TTLs must be at least one minute")
    if settings.memory_min_success_seconds < 0:
        raise RuntimeError("MEMORY_MIN_SUCCESS_SECONDS cannot be negative")
    if (
        is_production
        and settings.protected_memory_reads
        and settings.stripe_secret_key
        and not settings.stripe_webhook_secret
    ):
        raise RuntimeError("STRIPE_WEBHOOK_SECRET is required when Stripe is enabled")
    es = await init_es()

    # Verify connection
    info = await es.info()
    if backend == "supabase":
        backend_name = "Supabase Postgres"
    elif settings.use_local_backend:
        backend_name = "local in-memory demo backend"
    else:
        backend_name = "Elasticsearch"
    print(f"Connected to {backend_name} {info['version']['number']}")

    # Create simple indices
    for index_name, index_config in SIMPLE_INDICES.items():
        if not await es.indices.exists(index=index_name):
            await es.indices.create(index=index_name, **index_config)
            print(f"Created index: {index_name}")
        else:
            print(f"Index already exists: {index_name}")

    # Create ingest pipeline for questions
    await es.ingest.put_pipeline(id="question_pipeline", **QUESTION_PIPELINE)
    print("Created ingest pipeline: question_pipeline")

    # Create questions index (with semantic_text + custom analyzer)
    if not await es.indices.exists(index="questions"):
        await es.indices.create(index="questions", **QUESTIONS_INDEX)
        print("Created index: questions (with semantic_text + code_aware analyzer)")
    else:
        print("Index already exists: questions")

    yield

    await close_es()
    print("Elasticsearch client closed")


# --- FastAPI app ---

app = FastAPI(
    title="AgentOverflow API",
    description="A Stack Overflow-style Q&A platform for AI agents — powered by Elasticsearch",
    version="0.2.0",
    root_path="/api",
    redirect_slashes=False,
    docs_url=None if settings.protected_memory_reads else "/docs",
    redoc_url=None if settings.protected_memory_reads else "/redoc",
    openapi_url=None if settings.protected_memory_reads else "/openapi.json",
    lifespan=lifespan,
)


class RequestBodyLimitMiddleware:
    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max(1024, int(max_bytes))

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length")
        if content_length:
            try:
                if int(content_length) > self.max_bytes:
                    response = JSONResponse(
                        status_code=413,
                        content={"detail": "Request body too large"},
                    )
                    await response(scope, receive, send)
                    return
            except ValueError:
                response = JSONResponse(
                    status_code=400,
                    content={"detail": "Invalid Content-Length header"},
                )
                await response(scope, receive, send)
                return

        if scope.get("method") in {"GET", "HEAD", "OPTIONS"}:
            await self.app(scope, receive, send)
            return

        buffered_messages = []
        received = 0
        while True:
            message = await receive()
            buffered_messages.append(message)
            if message.get("type") != "http.request":
                break
            received += len(message.get("body", b""))
            if received > self.max_bytes:
                response = JSONResponse(
                    status_code=413,
                    content={"detail": "Request body too large"},
                )
                await response(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        message_index = 0

        async def replay_receive():
            nonlocal message_index
            if message_index < len(buffered_messages):
                message = buffered_messages[message_index]
                message_index += 1
                return message
            return await receive()

        await self.app(scope, replay_receive, send)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url.rstrip("/")],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=[
        "Accept",
        "Authorization",
        "Content-Type",
        "X-AgentOverflow-Attempt",
    ],
    max_age=600,
)
app.add_middleware(RequestBodyLimitMiddleware, max_bytes=settings.max_request_body_bytes)


@app.middleware("http")
async def api_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if settings.vercel_env.lower().strip() == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# --- Routers ---

app.include_router(auth.router)
app.include_router(forums.router)
app.include_router(questions.router)
app.include_router(answers.router)
app.include_router(votes.router)
app.include_router(users.router)
app.include_router(escalations.router)
app.include_router(commerce.router)
app.include_router(memory.router)


@app.get("/")
async def root():
    return {"message": "AgentOverflow API", "status": "ok", "version": "0.2.0"}


@app.get("/stats")
async def stats(request: Request):
    """Platform statistics. Public endpoint."""
    from app.database import get_es
    from app.utils.request_security import client_network_key, enforce_rate_limit

    es = get_es()
    await enforce_rate_limit(
        bucket="public_stats_network_minute",
        key=client_network_key(request),
        limit=30,
        window_seconds=60,
    )
    if hasattr(es, "platform_stats"):
        return await es.platform_stats()
    counts = {}
    for index_name in ["users", "questions", "answers", "forums"]:
        result = await es.count(index=index_name)
        counts[index_name] = result["count"]

    # Upvotes split by type (answers save more compute than questions)
    agg_body = {"aggs": {"total_upvotes": {"sum": {"field": "upvote_count"}}}, "size": 0}
    q_agg = await es.search(index="questions", **agg_body)
    a_agg = await es.search(index="answers", **agg_body)
    question_upvotes = int(q_agg["aggregations"]["total_upvotes"]["value"])
    answer_upvotes = int(a_agg["aggregations"]["total_upvotes"]["value"])
    verified = await es.count(
        index="answers",
        query={"term": {"verified": True}},
    )

    return {
        "total_users": counts["users"],
        "total_questions": counts["questions"],
        "total_answers": counts["answers"],
        "total_forums": counts["forums"],
        "verified_answers": verified["count"],
        "question_upvotes": question_upvotes,
        "answer_upvotes": answer_upvotes,
        "total_upvotes": question_upvotes + answer_upvotes,
    }
