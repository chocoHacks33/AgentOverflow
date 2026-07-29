from __future__ import annotations

import json
import math
import secrets
import hashlib
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

try:
    import asyncpg
except ImportError:  # pragma: no cover - only reached before dependencies are installed.
    asyncpg = None

from app.local_store import LocalNotFound, _contains_code, _doc_hit, _word_count
from app.config import settings
from app.utils.content_security import inspect_public_content
from app.utils.retrieval import feature_hash_embedding, pgvector_literal


def _decode_source(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return json.loads(value)
    return dict(value or {})


def _hash_api_key(encoded_key: str) -> str:
    return hashlib.sha256(encoded_key.encode("utf-8")).hexdigest()


class _SupabaseIndices:
    def __init__(self, parent: "SupabasePostgres"):
        self.parent = parent

    async def exists(self, index: str) -> bool:
        await self.parent.ensure_schema()
        return True

    async def create(self, index: str, **_: Any) -> dict[str, bool]:
        await self.parent.ensure_schema()
        return {"acknowledged": True}


class _SupabaseIngest:
    async def put_pipeline(self, id: str, **_: Any) -> dict[str, bool]:
        return {"acknowledged": True}


class _SupabaseSecurity:
    def __init__(self, parent: "SupabasePostgres", api_key: str | None = None):
        self.parent = parent
        self.api_key = api_key

    async def authenticate(self) -> dict[str, Any]:
        pool = await self.parent.ensure_pool()
        row = await pool.fetchrow(
            """
            select id
            from agentoverflow_api_keys
            where encoded_key_hash = $1
              and revoked_at is null
              and (expires_at is null or expires_at > now())
            """,
            _hash_api_key(self.api_key or ""),
        )
        if not row:
            raise LocalNotFound("Invalid API key")
        await pool.execute(
            "update agentoverflow_api_keys set last_used_at = now() where id = $1",
            row["id"],
        )
        return {"api_key": {"id": row["id"]}}

    async def create_api_key(self, name: str, metadata: dict[str, Any], **_: Any) -> dict[str, str]:
        pool = await self.parent.ensure_pool()
        key_id = await self.parent.next_id("api_key")
        encoded = f"ao_{secrets.token_urlsafe(32)}"
        await pool.execute(
            """
            insert into agentoverflow_api_keys (
                id, encoded_key_hash, name, metadata, expires_at
            )
            values (
                $1, $2, $3, $4::jsonb,
                now() + make_interval(days => $5)
            )
            """,
            key_id,
            _hash_api_key(encoded),
            name,
            json.dumps(metadata),
            settings.api_key_ttl_days,
        )
        return {"id": key_id, "encoded": encoded}

    async def get_api_key(self, id: str) -> dict[str, Any]:
        pool = await self.parent.ensure_pool()
        row = await pool.fetchrow(
            """
            select metadata
            from agentoverflow_api_keys
            where id = $1
              and revoked_at is null
              and (expires_at is null or expires_at > now())
            """,
            id,
        )
        if not row:
            raise LocalNotFound("API key not found")
        return {"api_keys": [{"id": id, "metadata": _decode_source(row["metadata"])}]}


class _SupabaseOptions:
    def __init__(self, parent: "SupabasePostgres", api_key: str):
        self.security = _SupabaseSecurity(parent, api_key=api_key)


class SupabasePostgres:
    """Persistent Postgres/pgvector-backed stand-in for the Elasticsearch API used by the app."""

    def __init__(
        self,
        database_url: str,
        min_size: int = 1,
        max_size: int = 5,
        auto_migrate: bool = True,
    ):
        self.database_url = database_url
        self.min_size = min_size
        self.max_size = max_size
        self.auto_migrate = auto_migrate
        self.pool: Any | None = None
        self._schema_ready = False
        self.indices = _SupabaseIndices(self)
        self.ingest = _SupabaseIngest()
        self.security = _SupabaseSecurity(self)
        self._embedding_backfill_checked = False

    async def ensure_pool(self) -> Any:
        if asyncpg is None:
            raise RuntimeError("asyncpg is required when STORAGE_BACKEND=supabase")
        if not self.database_url:
            raise RuntimeError("SUPABASE_DATABASE_URL is required when STORAGE_BACKEND=supabase")
        if self.pool is None:
            self.pool = await asyncpg.create_pool(
                self.database_url,
                min_size=self.min_size,
                max_size=self.max_size,
                command_timeout=30,
                statement_cache_size=0,
            )
        return self.pool

    async def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        pool = await self.ensure_pool()
        if not self.auto_migrate:
            async with pool.acquire() as conn:
                await conn.fetchval("select 1")
            self._schema_ready = True
            return
        async with pool.acquire() as conn:
            try:
                await conn.execute("create extension if not exists vector")
            except Exception:
                pass
            await conn.execute("create extension if not exists pg_trgm")
            await conn.execute(
                """
                create table if not exists agentoverflow_documents (
                    index_name text not null,
                    doc_id text not null,
                    source jsonb not null,
                    embedding vector(1536),
                    created_at timestamptz not null default now(),
                    updated_at timestamptz not null default now(),
                    primary key (index_name, doc_id)
                )
                """
            )
            await conn.execute(
                """
                create index if not exists agentoverflow_documents_source_gin
                on agentoverflow_documents using gin (source)
                """
            )
            await conn.execute(
                """
                create index if not exists agentoverflow_documents_index_name_idx
                on agentoverflow_documents (index_name)
                """
            )
            try:
                await conn.execute(
                    """
                    create index if not exists agentoverflow_documents_embedding_hnsw
                    on agentoverflow_documents using hnsw (embedding vector_cosine_ops)
                    where index_name = 'questions' and embedding is not null
                    """
                )
            except Exception:
                pass
            await conn.execute(
                """
                create table if not exists agentoverflow_api_keys (
                    id text primary key,
                    encoded_key_hash text not null unique,
                    name text not null,
                    metadata jsonb not null,
                    created_at timestamptz not null default now(),
                    expires_at timestamptz,
                    revoked_at timestamptz,
                    last_used_at timestamptz
                )
                """
            )
            await conn.execute(
                """
                alter table agentoverflow_api_keys
                    add column if not exists expires_at timestamptz,
                    add column if not exists revoked_at timestamptz,
                    add column if not exists last_used_at timestamptz
                """
            )
            await conn.execute(
                """
                create table if not exists agentoverflow_counters (
                    prefix text primary key,
                    value bigint not null
                )
                """
            )
            await conn.execute(
                """
                create table if not exists agentoverflow_rate_limits (
                    bucket text not null,
                    key_hash text not null,
                    window_start timestamptz not null,
                    request_count integer not null default 0,
                    primary key (bucket, key_hash, window_start)
                )
                """
            )
            await conn.execute(
                """
                create table if not exists agentoverflow_security_events (
                    id bigint generated always as identity primary key,
                    event_type text not null,
                    actor_hash text not null,
                    detail jsonb not null default '{}'::jsonb,
                    created_at timestamptz not null default now()
                )
                """
            )
        self._schema_ready = True

    def options(self, api_key: str) -> _SupabaseOptions:
        return _SupabaseOptions(self, api_key)

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None
            self._schema_ready = False

    async def info(self) -> dict[str, Any]:
        await self.ensure_schema()
        return {"version": {"number": "supabase-postgres"}}

    async def consume_rate_limit(
        self,
        bucket: str,
        key_hash: str,
        limit: int,
        window_seconds: int,
    ) -> tuple[bool, int, int]:
        await self.ensure_schema()
        pool = await self.ensure_pool()
        now = datetime.now(timezone.utc)
        epoch = int(now.timestamp())
        window_epoch = epoch - (epoch % window_seconds)
        window_start = datetime.fromtimestamp(window_epoch, timezone.utc)
        count = await pool.fetchval(
            """
            insert into agentoverflow_rate_limits (bucket, key_hash, window_start, request_count)
            values ($1, $2, $3, 1)
            on conflict (bucket, key_hash, window_start)
            do update set request_count = agentoverflow_rate_limits.request_count + 1
            returning request_count
            """,
            bucket,
            key_hash,
            window_start,
        )
        retry_after = max(1, window_epoch + window_seconds - epoch)
        return int(count) <= limit, max(0, limit - int(count)), retry_after

    async def record_security_event(
        self,
        event_type: str,
        actor_hash: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        await self.ensure_schema()
        pool = await self.ensure_pool()
        await pool.execute(
            """
            insert into agentoverflow_security_events (event_type, actor_hash, detail)
            values ($1, $2, $3::jsonb)
            """,
            event_type,
            actor_hash,
            json.dumps(detail or {}),
        )

    async def next_id(self, prefix: str) -> str:
        await self.ensure_schema()
        pool = await self.ensure_pool()
        value = await pool.fetchval(
            """
            insert into agentoverflow_counters (prefix, value)
            values ($1, 1)
            on conflict (prefix)
            do update set value = agentoverflow_counters.value + 1
            returning value
            """,
            prefix,
        )
        return f"{prefix}_{value}"

    async def count(self, index: str, query: dict[str, Any] | None = None, **_: Any) -> dict[str, int]:
        docs = await self._load_docs(index)
        if query:
            docs = [doc for doc in docs if self._matches(doc[1], query, None)]
        return {"count": len(docs)}

    async def index(
        self,
        index: str,
        document: dict[str, Any],
        id: str | None = None,
        pipeline: str | None = None,
        **_: Any,
    ) -> dict[str, str]:
        await self.ensure_schema()
        pool = await self.ensure_pool()
        doc_id = id or await self.next_id(index.rstrip("s") or index)
        doc = deepcopy(document)
        if index == "questions" or pipeline == "question_pipeline":
            doc["word_count"] = _word_count(doc.get("body", ""))
            doc["has_code"] = _contains_code(doc.get("body", ""))
        embedding = None
        if index == "questions":
            embedding = pgvector_literal(
                feature_hash_embedding(
                    f"{doc.get('title', '')}\n{doc.get('body', '')}\n{doc.get('forum_name', '')}"
                )
            )
        await pool.execute(
            """
            insert into agentoverflow_documents (index_name, doc_id, source, embedding)
            values ($1, $2, $3::jsonb, $4::vector)
            on conflict (index_name, doc_id)
            do update set source = excluded.source, embedding = excluded.embedding, updated_at = now()
            """,
            index,
            doc_id,
            json.dumps(doc),
            embedding,
        )
        return {"_id": doc_id}

    async def hybrid_memory_search(
        self,
        query_text: str,
        *,
        forum_id: str | None = None,
        size: int = 8,
    ) -> list[dict[str, Any]]:
        await self.ensure_schema()
        await self._backfill_missing_question_embeddings()
        pool = await self.ensure_pool()
        query_embedding = pgvector_literal(feature_hash_embedding(query_text))
        rows = await pool.fetch(
            """
            with ranked as (
                select
                    doc_id,
                    source,
                    updated_at,
                    ts_rank_cd(
                        to_tsvector(
                            'simple',
                            coalesce(source->>'title', '') || ' ' ||
                            coalesce(source->>'body', '') || ' ' ||
                            coalesce(source->>'forum_name', '')
                        ),
                        plainto_tsquery('simple', $1)
                    ) as fts_score,
                    greatest(
                        similarity(lower(coalesce(source->>'title', '')), lower($1)),
                        word_similarity(lower($1), lower(
                            coalesce(source->>'title', '') || ' ' ||
                            coalesce(source->>'body', '')
                        ))
                    ) as trigram_score,
                    case
                        when embedding is null then 0.0
                        else greatest(0.0, 1.0 - (embedding <=> $2::vector))
                    end as vector_score
                from agentoverflow_documents
                where index_name = 'questions'
                  and ($3::text is null or source->>'forum_id' = $3)
                  and coalesce(source->>'moderation_status', 'accepted') <> 'quarantined'
            )
            select
                doc_id,
                source,
                updated_at,
                least(
                    1.0,
                    (fts_score * 0.45) +
                    (trigram_score * 0.20) +
                    (vector_score * 0.35)
                ) as combined_score
            from ranked
            where fts_score > 0
               or trigram_score >= 0.12
               or vector_score >= 0.20
            order by
                combined_score desc,
                coalesce((source->>'verified_answer_count')::integer, 0) desc,
                coalesce((source->>'score')::integer, 0) desc,
                updated_at desc nulls last
            limit $4
            """,
            query_text,
            query_embedding,
            forum_id,
            max(1, min(int(size), 20)),
        )
        return [
            _doc_hit(
                row["doc_id"],
                _decode_source(row["source"]),
                float(row["combined_score"] or 0.0),
            )
            for row in rows
        ]

    async def _backfill_missing_question_embeddings(self, limit: int = 200) -> None:
        if self._embedding_backfill_checked:
            return
        pool = await self.ensure_pool()
        rows = await pool.fetch(
            """
            select doc_id, source
            from agentoverflow_documents
            where index_name = 'questions' and embedding is null
            order by created_at
            limit $1
            """,
            limit,
        )
        for row in rows:
            source = _decode_source(row["source"])
            public_text = f"{source.get('title', '')}\n{source.get('body', '')}"
            if inspect_public_content(public_text):
                source["moderation_status"] = "quarantined"
                await pool.execute(
                    """
                    update agentoverflow_documents
                    set source = $2::jsonb, updated_at = now()
                    where index_name = 'questions' and doc_id = $1 and embedding is null
                    """,
                    row["doc_id"],
                    json.dumps(source),
                )
                continue
            embedding = pgvector_literal(
                feature_hash_embedding(
                    f"{source.get('title', '')}\n{source.get('body', '')}\n{source.get('forum_name', '')}"
                )
            )
            await pool.execute(
                """
                update agentoverflow_documents
                set embedding = $2::vector, updated_at = now()
                where index_name = 'questions' and doc_id = $1 and embedding is null
                """,
                row["doc_id"],
                embedding,
            )
        self._embedding_backfill_checked = len(rows) < limit

    async def claim_memory_attempt(self, attempt_id: str, user_id: str) -> bool:
        await self.ensure_schema()
        pool = await self.ensure_pool()
        result = await pool.execute(
            """
            update agentoverflow_documents
            set
                source = jsonb_set(source, '{status}', '"completing"'::jsonb),
                updated_at = now()
            where index_name = 'memory_attempts'
              and doc_id = $1
              and source->>'user_id' = $2
              and source->>'status' = 'in_progress'
            """,
            attempt_id,
            user_id,
        )
        return not result.endswith(" 0")

    async def consume_task_subtask(self, task_id: str, user_id: str, limit: int) -> bool:
        await self.ensure_schema()
        pool = await self.ensure_pool()
        result = await pool.execute(
            """
            update agentoverflow_documents
            set
                source = jsonb_set(
                    source,
                    '{subtask_count}',
                    to_jsonb(coalesce((source->>'subtask_count')::integer, 0) + 1)
                ),
                updated_at = now()
            where index_name = 'memory_tasks'
              and doc_id = $1
              and source->>'user_id' = $2
              and coalesce((source->>'subtask_count')::integer, 0) < $3
            """,
            task_id,
            user_id,
            limit,
        )
        return not result.endswith(" 0")

    async def platform_stats(self) -> dict[str, int]:
        await self.ensure_schema()
        pool = await self.ensure_pool()
        row = await pool.fetchrow(
            """
            select
                count(*) filter (where index_name = 'users') as total_users,
                count(*) filter (where index_name = 'questions') as total_questions,
                count(*) filter (where index_name = 'answers') as total_answers,
                count(*) filter (where index_name = 'forums') as total_forums,
                count(*) filter (
                    where index_name = 'answers' and coalesce((source->>'verified')::boolean, false)
                ) as verified_answers,
                coalesce(sum((source->>'upvote_count')::integer) filter (where index_name = 'questions'), 0)
                    as question_upvotes,
                coalesce(sum((source->>'upvote_count')::integer) filter (where index_name = 'answers'), 0)
                    as answer_upvotes
            from agentoverflow_documents
            where index_name in ('users', 'questions', 'answers', 'forums')
            """
        )
        question_upvotes = int(row["question_upvotes"] or 0)
        answer_upvotes = int(row["answer_upvotes"] or 0)
        return {
            "total_users": int(row["total_users"] or 0),
            "total_questions": int(row["total_questions"] or 0),
            "total_answers": int(row["total_answers"] or 0),
            "total_forums": int(row["total_forums"] or 0),
            "verified_answers": int(row["verified_answers"] or 0),
            "question_upvotes": question_upvotes,
            "answer_upvotes": answer_upvotes,
            "total_upvotes": question_upvotes + answer_upvotes,
        }

    async def get(self, index: str, id: str) -> dict[str, Any]:
        await self.ensure_schema()
        pool = await self.ensure_pool()
        row = await pool.fetchrow(
            """
            select source
            from agentoverflow_documents
            where index_name = $1 and doc_id = $2
            """,
            index,
            id,
        )
        if not row:
            raise LocalNotFound(f"{index}/{id} not found")
        return _doc_hit(id, _decode_source(row["source"]))

    async def delete(self, index: str, id: str, **_: Any) -> dict[str, str]:
        await self.ensure_schema()
        pool = await self.ensure_pool()
        result = await pool.execute(
            """
            delete from agentoverflow_documents
            where index_name = $1 and doc_id = $2
            """,
            index,
            id,
        )
        if result.endswith(" 0"):
            raise LocalNotFound(f"{index}/{id} not found")
        return {"result": "deleted"}

    async def mget(self, index: str, ids: list[str]) -> dict[str, Any]:
        await self.ensure_schema()
        pool = await self.ensure_pool()
        rows = await pool.fetch(
            """
            select doc_id, source
            from agentoverflow_documents
            where index_name = $1 and doc_id = any($2::text[])
            """,
            index,
            ids,
        )
        found = {row["doc_id"]: _decode_source(row["source"]) for row in rows}
        docs = []
        for doc_id in ids:
            if doc_id in found:
                docs.append({"_id": doc_id, "found": True, "_source": found[doc_id]})
            else:
                docs.append({"_id": doc_id, "found": False})
        return {"docs": docs}

    async def update(
        self,
        index: str,
        id: str,
        script: dict[str, Any] | None = None,
        doc: dict[str, Any] | None = None,
        **_: Any,
    ) -> dict[str, str]:
        await self.ensure_schema()
        pool = await self.ensure_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    select source
                    from agentoverflow_documents
                    where index_name = $1 and doc_id = $2
                    for update
                    """,
                    index,
                    id,
                )
                if not row:
                    raise LocalNotFound(f"{index}/{id} not found")
                target = _decode_source(row["source"])
                if doc:
                    target.update(doc)
                if script:
                    source = script.get("source", "")
                    params = script.get("params", {})
                    if "question_count += 1" in source:
                        target["question_count"] = int(target.get("question_count", 0)) + 1
                    if "answer_count += 1" in source:
                        target["answer_count"] = int(target.get("answer_count", 0)) + 1
                    if "upvote_count" in source and "up_delta" in params:
                        target["upvote_count"] = int(target.get("upvote_count", 0)) + int(params.get("up_delta", 0))
                        target["downvote_count"] = int(target.get("downvote_count", 0)) + int(params.get("down_delta", 0))
                        target["score"] = target.get("upvote_count", 0) - target.get("downvote_count", 0)
                await conn.execute(
                    """
                    update agentoverflow_documents
                    set source = $3::jsonb, updated_at = now()
                    where index_name = $1 and doc_id = $2
                    """,
                    index,
                    id,
                    json.dumps(target),
                )
        return {"result": "updated"}

    async def search(
        self,
        index: str,
        query: dict[str, Any] | None = None,
        sort: list[dict[str, dict[str, str]]] | None = None,
        from_: int = 0,
        size: int = 10,
        retriever: dict[str, Any] | None = None,
        aggs: dict[str, Any] | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        docs = await self._load_docs(index)
        search_text = self._extract_search_text(query, retriever)
        docs = [x for x in docs if self._matches(x[1], query, retriever)]
        scored = [(doc_id, src, self._score(src, search_text)) for doc_id, src in docs]
        if search_text:
            scored = [x for x in scored if x[2] > 0]
            scored.sort(key=lambda x: (x[2], x[1].get("score", 0)), reverse=True)
        elif sort:
            scored = self._sort(scored, sort)
        hits = [_doc_hit(doc_id, src, score) for doc_id, src, score in scored[from_: from_ + size]]
        result: dict[str, Any] = {
            "hits": {
                "total": {"value": len(scored)},
                "hits": hits,
            }
        }
        if aggs:
            result["aggregations"] = {
                name: {"value": sum(int(src.get(spec["sum"]["field"], 0)) for _, src, _ in scored)}
                for name, spec in aggs.items()
                if "sum" in spec
            }
        return result

    async def _load_docs(self, index: str) -> list[tuple[str, dict[str, Any]]]:
        await self.ensure_schema()
        pool = await self.ensure_pool()
        rows = await pool.fetch(
            """
            select doc_id, source
            from agentoverflow_documents
            where index_name = $1
            """,
            index,
        )
        return [(row["doc_id"], _decode_source(row["source"])) for row in rows]

    def _extract_search_text(self, query: dict[str, Any] | None, retriever: dict[str, Any] | None) -> str:
        if query and "multi_match" in query:
            return str(query["multi_match"].get("query", ""))
        if retriever:
            return str(retriever).split("'query': '", 1)[-1].split("'", 1)[0] if "'query': '" in str(retriever) else ""
        return ""

    def _matches(self, src: dict[str, Any], query: dict[str, Any] | None, retriever: dict[str, Any] | None) -> bool:
        if retriever:
            filter_term = self._extract_filter_term(retriever)
            return not filter_term or all(str(src.get(k)) == str(v) for k, v in filter_term.items())
        if not query or "match_all" in query:
            return True
        if "term" in query:
            return all(str(src.get(k)) == str(v) for k, v in query["term"].items())
        if "wildcard" in query:
            for field, spec in query["wildcard"].items():
                needle = str(spec.get("value", "")).replace("*", "").lower()
                if needle not in str(src.get(field, "")).lower():
                    return False
            return True
        if "bool" in query:
            for item in query["bool"].get("filter", []):
                if "term" in item and not self._matches(src, item, None):
                    return False
            return True
        return True

    def _extract_filter_term(self, retriever: dict[str, Any]) -> dict[str, Any]:
        rrf = retriever.get("rrf") or retriever.get("text_similarity_reranker", {}).get("retriever", {}).get("rrf")
        if not rrf:
            return {}
        filt = rrf.get("filter", {})
        return filt.get("term", {}) if isinstance(filt, dict) else {}

    def _score(self, src: dict[str, Any], search_text: str) -> float:
        if not search_text:
            return 1.0
        haystack = " ".join(str(src.get(k, "")) for k in ["title", "body", "forum_name", "username", "name"]).lower()
        terms = [t for t in search_text.lower().replace("/", " ").replace("-", " ").split() if len(t) > 1]
        if not terms:
            return 1.0
        matches = sum(1 for t in terms if t in haystack)
        return matches / math.sqrt(len(terms))

    def _sort(
        self,
        scored: list[tuple[str, dict[str, Any], float]],
        sort: list[dict[str, dict[str, str]]],
    ) -> list[tuple[str, dict[str, Any], float]]:
        for clause in reversed(sort):
            field, opts = next(iter(clause.items()))
            reverse = opts.get("order", "asc") == "desc"
            scored.sort(key=lambda x: x[1].get(field, 0), reverse=reverse)
        return scored
