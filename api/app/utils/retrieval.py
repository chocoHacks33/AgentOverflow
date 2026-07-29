from __future__ import annotations

import hashlib
import math
import re
from collections import Counter


VECTOR_DIMENSIONS = 1536

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_+.#:/-]*", re.IGNORECASE)
_STOPWORDS = {
    "a",
    "about",
    "after",
    "again",
    "agent",
    "agents",
    "all",
    "also",
    "an",
    "and",
    "any",
    "app",
    "are",
    "as",
    "at",
    "be",
    "because",
    "before",
    "being",
    "but",
    "by",
    "can",
    "code",
    "context",
    "could",
    "do",
    "does",
    "done",
    "each",
    "ensure",
    "error",
    "exact",
    "for",
    "from",
    "genuine",
    "goal",
    "has",
    "have",
    "how",
    "if",
    "implementation",
    "in",
    "into",
    "is",
    "it",
    "its",
    "memory",
    "must",
    "new",
    "no",
    "not",
    "of",
    "on",
    "one",
    "only",
    "or",
    "other",
    "our",
    "plugin",
    "problem",
    "project",
    "repository",
    "result",
    "same",
    "server",
    "should",
    "specific",
    "subtask",
    "success",
    "task",
    "test",
    "tests",
    "that",
    "the",
    "their",
    "then",
    "this",
    "through",
    "to",
    "use",
    "used",
    "user",
    "using",
    "validate",
    "when",
    "where",
    "which",
    "while",
    "with",
    "without",
    "work",
}

_TOKEN_ALIASES = {
    "authn": "authentication",
    "authz": "authorization",
    "ci": "continuous-integration",
    "cli": "command-line",
    "db": "database",
    "deps": "dependencies",
    "js": "javascript",
    "k8s": "kubernetes",
    "postgres": "postgresql",
    "py": "python",
    "ts": "typescript",
}


def _is_signature_token(token: str) -> bool:
    return (
        len(token) >= 18
        or (
            len(token) >= 8
            and any(char.isalpha() for char in token)
            and any(char.isdigit() for char in token)
        )
        or (len(token) >= 8 and any(char in token for char in "._+#/-"))
    )


def normalized_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for raw in _TOKEN_RE.findall(str(text or "").lower()):
        token = raw.strip("./:-")
        if len(token) < 2 or token in _STOPWORDS:
            continue
        tokens.append(_TOKEN_ALIASES.get(token, token))
    return tokens


def query_is_specific(text: str) -> bool:
    tokens = normalized_tokens(text)
    unique = set(tokens)
    distinctive = [token for token in unique if len(token) >= 5 or any(char in token for char in "._+#/-")]
    has_unique_signature = any(_is_signature_token(token) for token in unique)
    return (len(unique) >= 3 and len(distinctive) >= 2) or (
        len(unique) >= 2 and has_unique_signature
    )


def relevance_score(query: str, title: str, body: str, backend_score: float = 0.0) -> float:
    query_tokens = normalized_tokens(query)
    document_tokens = normalized_tokens(f"{title} {body}")
    if not query_tokens or not document_tokens:
        return 0.0

    query_set = set(query_tokens)
    document_set = set(document_tokens)
    overlap = query_set & document_set
    distinctive_overlap = {
        token
        for token in overlap
        if len(token) >= 6 or any(char in token for char in "._+#/-")
    }
    coverage = len(overlap) / max(1, min(len(query_set), 16))
    precision = len(overlap) / max(1, min(len(document_set), 40))
    exact_title = " ".join(query_tokens[:8]) in " ".join(document_tokens[:20])
    unique_sentinel = any(_is_signature_token(token) and token in document_set for token in query_set)

    lexical = min(1.0, (coverage * 0.68) + (precision * 0.22))
    backend = max(0.0, min(float(backend_score or 0.0), 1.0))
    score = lexical + (backend * 0.10)
    if exact_title:
        score += 0.18
    if unique_sentinel:
        score += 0.25
    if len(distinctive_overlap) >= 2:
        score += 0.12
    return min(1.0, score)


def is_relevant_match(
    query: str,
    title: str,
    body: str,
    backend_score: float = 0.0,
    *,
    minimum_score: float = 0.26,
) -> bool:
    query_set = set(normalized_tokens(query))
    document_set = set(normalized_tokens(f"{title} {body}"))
    signatures = {
        token
        for token in query_set
        if _is_signature_token(token)
    }
    if signatures and not (signatures & document_set):
        return False
    overlap = query_set & document_set
    coverage = len(overlap) / max(1, min(len(query_set), 16))
    distinctive = [
        token
        for token in overlap
        if len(token) >= 6 or any(char in token for char in "._+#/-")
    ]
    has_unique_sentinel = any(
        _is_signature_token(token) and token in document_set
        for token in query_set
    )
    if len(overlap) < 2 and not has_unique_sentinel:
        return False
    if coverage < 0.30 and not has_unique_sentinel:
        return False
    if not distinctive and len(overlap) < 3:
        return False
    return relevance_score(query, title, body, backend_score) >= minimum_score


def feature_hash_embedding(text: str, dimensions: int = VECTOR_DIMENSIONS) -> list[float]:
    tokens = normalized_tokens(text)
    features = list(tokens)
    features.extend(f"{left}::{right}" for left, right in zip(tokens, tokens[1:]))
    for token in set(tokens):
        compact = re.sub(r"[^a-z0-9+#.]", "", token)
        if len(compact) >= 5:
            features.extend(f"char:{compact[index:index + 4]}" for index in range(len(compact) - 3))
    if not features:
        return [0.0] * dimensions

    counts = Counter(features)
    vector = [0.0] * dimensions
    for feature, count in counts.items():
        digest = hashlib.sha256(feature.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        sign = -1.0 if digest[4] & 1 else 1.0
        weight = 1.0 + math.log(float(count))
        vector[index] += sign * weight

    norm = math.sqrt(sum(value * value for value in vector))
    if norm:
        vector = [value / norm for value in vector]
    return vector


def pgvector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"
