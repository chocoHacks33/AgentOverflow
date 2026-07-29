from __future__ import annotations

import json
import math
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "api"))

from app.utils.retrieval import (  # noqa: E402
    VECTOR_DIMENSIONS,
    feature_hash_embedding,
    is_relevant_match,
    relevance_score,
)


CASES = [
    (
        "TypeScript pnpm lockfile peer dependency conflict in Next.js 16 install",
        "Resolve npm ERESOLVE peer dependency conflict in a Next.js TypeScript monorepo",
        [
            "Fix a Next.js route handler cache invalidation bug",
            "Repair TypeScript source maps in Vitest",
        ],
    ),
    (
        "asyncpg connection pool exhausted timeout in Supabase FastAPI",
        "Prevent asyncpg pool acquisition timeouts in a FastAPI Supabase service",
        [
            "Configure Supabase row level security for tenant records",
            "Handle FastAPI validation error responses",
        ],
    ),
    (
        "pytest monkeypatch environment variable remains after test cleanup",
        "Restore process environment after pytest monkeypatch test isolation",
        [
            "Speed up pytest collection with cached fixtures",
            "Mock HTTP requests in pytest",
        ],
    ),
    (
        "React hydration mismatch caused by Date.now server client rendering",
        "Replace Date.now during server rendering to remove the React hydration mismatch",
        [
            "Fix React stale closure in an interval hook",
            "Memoize an expensive React component",
        ],
    ),
    (
        "Docker multi-stage build cannot find pnpm workspace package module",
        "Copy pnpm workspace manifests before Docker multi-stage install",
        [
            "Reduce Docker image size with a distroless runtime",
            "Configure pnpm workspace linting",
        ],
    ),
    (
        "Pydantic extra fields should reject mass assignment payload",
        "Forbid unknown Pydantic fields to prevent mass assignment",
        [
            "Serialize optional Pydantic fields in API responses",
            "Generate Pydantic JSON schema",
        ],
    ),
    (
        "SQLAlchemy DetachedInstanceError when lazy relationship is accessed after session closes",
        "Fix SQLAlchemy DetachedInstanceError by eager loading the relationship before session close",
        [
            "Tune SQLAlchemy connection pool recycling",
            "Create an Alembic database migration",
        ],
    ),
    (
        "Rust cargo feature resolver selects duplicate incompatible dependency versions",
        "Unify Cargo feature flags and dependency versions under resolver two",
        [
            "Reduce Rust binary size in release builds",
            "Fix Cargo registry authentication",
        ],
    ),
    (
        "Redis distributed lock expires while worker still processes job",
        "Renew the Redis lock lease while the long-running worker owns it",
        [
            "Configure Redis eviction policy for cache keys",
            "Serialize a job payload into Redis",
        ],
    ),
    (
        "Playwright locator click fails because overlay intercepts pointer events",
        "Wait for the overlay to detach before clicking the Playwright locator",
        [
            "Capture Playwright screenshots on test failure",
            "Configure a mobile Playwright viewport",
        ],
    ),
    (
        "Python ModuleNotFoundError after editable install with src layout",
        "Fix ModuleNotFoundError by declaring the src package in pyproject and reinstalling editable",
        [
            "Pin Python transitive dependencies with hashes",
            "Fix Python circular imports",
        ],
    ),
    (
        "PostgreSQL deadlock during concurrent account balance row updates",
        "Prevent the PostgreSQL deadlock by ordering concurrent account row updates",
        [
            "Create a PostgreSQL GIN index for text search",
            "Enable PostgreSQL row level security",
        ],
    ),
]


def cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def score(query: str, document: str) -> tuple[float, bool]:
    backend_score = cosine(
        feature_hash_embedding(query),
        feature_hash_embedding(document),
    )
    return (
        relevance_score(query, document, "", backend_score),
        is_relevant_match(query, document, "", backend_score),
    )


def main() -> None:
    positive_relevant = 0
    negative_rejected = 0
    top_one_correct = 0
    negative_count = 0
    margins: list[float] = []

    for query, positive, negatives in CASES:
        positive_score, positive_match = score(query, positive)
        negative_results = [score(query, negative) for negative in negatives]
        positive_relevant += int(positive_match)
        negative_rejected += sum(int(not relevant) for _, relevant in negative_results)
        negative_count += len(negative_results)
        strongest_negative = max(value for value, _ in negative_results)
        top_one_correct += int(positive_score > strongest_negative)
        margins.append(positive_score - strongest_negative)

    sample_vector = feature_hash_embedding("agentoverflow retrieval vector integrity")
    vector_integrity = (
        len(sample_vector) == VECTOR_DIMENSIONS
        and abs(math.sqrt(sum(value * value for value in sample_vector)) - 1.0) < 1e-6
    )
    result = {
        "ok": (
            positive_relevant == len(CASES)
            and negative_rejected == negative_count
            and top_one_correct == len(CASES)
            and vector_integrity
        ),
        "cases": len(CASES),
        "positive_recall": round(positive_relevant / len(CASES), 4),
        "hard_negative_rejection": round(negative_rejected / negative_count, 4),
        "top_one_accuracy": round(top_one_correct / len(CASES), 4),
        "minimum_score_margin": round(min(margins), 4),
        "vector_dimensions": len(sample_vector),
        "vector_integrity": vector_integrity,
        "note": (
            "This is a deterministic technical retrieval regression set, not a claim "
            "of universal semantic accuracy."
        ),
    }
    print(json.dumps(result, indent=2))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
