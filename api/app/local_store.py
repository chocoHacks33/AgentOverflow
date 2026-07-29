from __future__ import annotations

import math
import secrets
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any


class LocalNotFound(Exception):
    pass


def _now_minus(minutes: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def _contains_code(text: str) -> bool:
    return "```" in text


def _word_count(text: str) -> int:
    return len([x for x in text.split(" ") if x])


def _doc_hit(doc_id: str, source: dict[str, Any], score: float = 1.0) -> dict[str, Any]:
    return {"_id": doc_id, "_source": deepcopy(source), "_score": score}


class _LocalIndices:
    def __init__(self, parent: "LocalElasticsearch"):
        self.parent = parent

    async def exists(self, index: str) -> bool:
        return index in self.parent.data

    async def create(self, index: str, **_: Any) -> dict[str, bool]:
        self.parent.data.setdefault(index, {})
        return {"acknowledged": True}


class _LocalIngest:
    async def put_pipeline(self, id: str, **_: Any) -> dict[str, bool]:
        return {"acknowledged": True}


class _LocalSecurity:
    def __init__(self, parent: "LocalElasticsearch", api_key: str | None = None):
        self.parent = parent
        self.api_key = api_key

    async def authenticate(self) -> dict[str, Any]:
        key = self.parent.api_keys_by_encoded.get(self.api_key or "")
        if not key:
            raise LocalNotFound("Invalid API key")
        return {"api_key": {"id": key["id"]}}

    async def create_api_key(self, name: str, metadata: dict[str, Any], **_: Any) -> dict[str, str]:
        key_id = self.parent.next_id("api_key")
        encoded = f"local_{secrets.token_urlsafe(24)}"
        record = {"id": key_id, "name": name, "encoded": encoded, "metadata": metadata}
        self.parent.api_keys[key_id] = record
        self.parent.api_keys_by_encoded[encoded] = record
        return {"id": key_id, "encoded": encoded}

    async def get_api_key(self, id: str) -> dict[str, Any]:
        key = self.parent.api_keys.get(id)
        if not key:
            raise LocalNotFound("API key not found")
        return {"api_keys": [{"id": id, "metadata": key["metadata"]}]}


class _LocalOptions:
    def __init__(self, parent: "LocalElasticsearch", api_key: str):
        self.security = _LocalSecurity(parent, api_key=api_key)


class LocalElasticsearch:
    """Small async in-memory stand-in for the Elasticsearch API used by the app."""

    def __init__(self, seed_demo_data: bool = False):
        self.data: dict[str, dict[str, dict[str, Any]]] = {
            "users": {},
            "forums": {},
            "questions": {},
            "answers": {},
            "votes": {},
            "escalations": {},
        }
        self.api_keys: dict[str, dict[str, Any]] = {}
        self.api_keys_by_encoded: dict[str, dict[str, Any]] = {}
        self.counters: dict[str, int] = {}
        self.rate_limits: dict[tuple[str, str, int], int] = {}
        self.security_events: list[dict[str, Any]] = []
        self.indices = _LocalIndices(self)
        self.ingest = _LocalIngest()
        self.security = _LocalSecurity(self)
        if seed_demo_data:
            self._seed_demo_data()

    def next_id(self, prefix: str) -> str:
        self.counters[prefix] = self.counters.get(prefix, 0) + 1
        return f"{prefix}_{self.counters[prefix]}"

    def options(self, api_key: str) -> _LocalOptions:
        return _LocalOptions(self, api_key)

    async def close(self) -> None:
        return None

    async def info(self) -> dict[str, Any]:
        return {"version": {"number": "local-demo"}}

    async def consume_rate_limit(
        self,
        bucket: str,
        key_hash: str,
        limit: int,
        window_seconds: int,
    ) -> tuple[bool, int, int]:
        now_seconds = int(datetime.now(timezone.utc).timestamp())
        window_start = now_seconds - (now_seconds % window_seconds)
        key = (bucket, key_hash, window_start)
        count = self.rate_limits.get(key, 0) + 1
        self.rate_limits[key] = count
        retry_after = max(1, window_start + window_seconds - now_seconds)
        return count <= limit, max(0, limit - count), retry_after

    async def record_security_event(
        self,
        event_type: str,
        actor_hash: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self.security_events.append(
            {
                "event_type": event_type,
                "actor_hash": actor_hash,
                "detail": deepcopy(detail or {}),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    async def hybrid_memory_search(
        self,
        query_text: str,
        *,
        forum_id: str | None = None,
        size: int = 8,
    ) -> list[dict[str, Any]]:
        from app.utils.retrieval import relevance_score

        hits: list[dict[str, Any]] = []
        for doc_id, source in self.data.get("questions", {}).items():
            if forum_id and str(source.get("forum_id")) != str(forum_id):
                continue
            score = relevance_score(
                query_text,
                str(source.get("title", "")),
                str(source.get("body", "")),
            )
            if score <= 0:
                continue
            hits.append(_doc_hit(doc_id, source, score))
        hits.sort(
            key=lambda hit: (
                float(hit.get("_score", 0)),
                int(hit["_source"].get("score", 0)),
            ),
            reverse=True,
        )
        return hits[:size]

    async def claim_memory_attempt(self, attempt_id: str, user_id: str) -> bool:
        attempt = self.data.get("memory_attempts", {}).get(attempt_id)
        if not attempt:
            return False
        if attempt.get("user_id") != user_id or attempt.get("status") != "in_progress":
            return False
        attempt["status"] = "completing"
        return True

    async def consume_task_subtask(self, task_id: str, user_id: str, limit: int) -> bool:
        task = self.data.get("memory_tasks", {}).get(task_id)
        if not task or task.get("user_id") != user_id:
            return False
        count = int(task.get("subtask_count", 0))
        if count >= limit:
            return False
        task["subtask_count"] = count + 1
        return True

    async def platform_stats(self) -> dict[str, int]:
        question_upvotes = sum(
            int(source.get("upvote_count", 0))
            for source in self.data.get("questions", {}).values()
        )
        answer_upvotes = sum(
            int(source.get("upvote_count", 0))
            for source in self.data.get("answers", {}).values()
        )
        verified_answers = sum(
            1
            for source in self.data.get("answers", {}).values()
            if source.get("verified") is True
        )
        return {
            "total_users": len(self.data.get("users", {})),
            "total_questions": len(self.data.get("questions", {})),
            "total_answers": len(self.data.get("answers", {})),
            "total_forums": len(self.data.get("forums", {})),
            "verified_answers": verified_answers,
            "question_upvotes": question_upvotes,
            "answer_upvotes": answer_upvotes,
            "total_upvotes": question_upvotes + answer_upvotes,
        }

    async def count(self, index: str, query: dict[str, Any] | None = None, **_: Any) -> dict[str, int]:
        docs = self.data.get(index, {}).values()
        if query:
            docs = [doc for doc in docs if self._matches(doc, query, None)]
        return {"count": len(list(docs))}

    async def index(
        self,
        index: str,
        document: dict[str, Any],
        id: str | None = None,
        pipeline: str | None = None,
        **_: Any,
    ) -> dict[str, str]:
        self.data.setdefault(index, {})
        doc_id = id or self.next_id(index.rstrip("s") or index)
        doc = deepcopy(document)
        if index == "questions" or pipeline == "question_pipeline":
            doc["word_count"] = _word_count(doc.get("body", ""))
            doc["has_code"] = _contains_code(doc.get("body", ""))
        self.data[index][doc_id] = doc
        return {"_id": doc_id}

    async def get(self, index: str, id: str) -> dict[str, Any]:
        try:
            return _doc_hit(id, self.data[index][id])
        except KeyError as exc:
            raise LocalNotFound(f"{index}/{id} not found") from exc

    async def delete(self, index: str, id: str, **_: Any) -> dict[str, str]:
        try:
            del self.data[index][id]
        except KeyError as exc:
            raise LocalNotFound(f"{index}/{id} not found") from exc
        return {"result": "deleted"}

    async def mget(self, index: str, ids: list[str]) -> dict[str, Any]:
        docs = []
        for doc_id in ids:
            if doc_id in self.data.get(index, {}):
                docs.append({"_id": doc_id, "found": True, "_source": deepcopy(self.data[index][doc_id])})
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
        if id not in self.data.get(index, {}):
            raise LocalNotFound(f"{index}/{id} not found")
        target = self.data[index][id]
        if doc:
            target.update(doc)
        if script:
            source = script.get("source", "")
            params = script.get("params", {})
            if "question_count += 1" in source:
                target["question_count"] = target.get("question_count", 0) + 1
            if "answer_count += 1" in source:
                target["answer_count"] = target.get("answer_count", 0) + 1
            if "upvote_count" in source and "up_delta" in params:
                target["upvote_count"] = target.get("upvote_count", 0) + int(params.get("up_delta", 0))
                target["downvote_count"] = target.get("downvote_count", 0) + int(params.get("down_delta", 0))
                target["score"] = target.get("upvote_count", 0) - target.get("downvote_count", 0)
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
        docs = [(_id, deepcopy(src)) for _id, src in self.data.get(index, {}).items()]
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

    def _seed_demo_data(self) -> None:
        from app.seed_data import build_seed_data

        seed = build_seed_data()
        for index_name, documents in seed.items():
            self.data[index_name].update(documents)
        self.counters.update(
            {
                "user": len(seed["users"]),
                "forum": len(seed["forums"]),
                "question": len(seed["questions"]),
                "answer": len(seed["answers"]),
            }
        )
