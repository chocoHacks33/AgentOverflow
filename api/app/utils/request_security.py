from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os

from fastapi import HTTPException, Request

from app.config import settings
from app.database import get_es


def _hash_key(value: str) -> str:
    secret = settings.agentoverflow_access_secret.strip() or "agentoverflow-local-rate-limit"
    return hmac.new(
        secret.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def client_network_key(request: Request) -> str:
    provider = settings.trusted_proxy_provider.strip().lower()
    on_vercel = bool(settings.vercel_env or os.getenv("VERCEL"))
    trust_vercel = provider == "vercel" or (provider == "auto" and on_vercel)
    forwarded = request.headers.get("x-vercel-forwarded-for", "") if trust_vercel else ""
    candidate = forwarded.split(",", 1)[0].strip() if forwarded else ""
    if not candidate and request.client:
        candidate = request.client.host
    try:
        address = ipaddress.ip_address(candidate)
        if address.version == 6:
            candidate = str(ipaddress.ip_network(f"{address}/64", strict=False).network_address)
        else:
            candidate = str(address)
    except ValueError:
        candidate = request.client.host if request.client else "unknown-client"
    return _hash_key(candidate or "unknown-client")


def actor_key(*parts: str) -> str:
    return _hash_key(":".join(str(part) for part in parts))


async def enforce_rate_limit(
    *,
    bucket: str,
    key: str,
    limit: int,
    window_seconds: int,
) -> None:
    es = get_es()
    if not hasattr(es, "consume_rate_limit"):
        return
    allowed, remaining, retry_after = await es.consume_rate_limit(
        bucket,
        actor_key(bucket, key),
        max(1, int(limit)),
        max(1, int(window_seconds)),
    )
    if allowed:
        return
    if hasattr(es, "record_security_event"):
        await es.record_security_event(
            "rate_limit_exceeded",
            actor_key(key),
            {
                "bucket": bucket,
                "limit": limit,
                "window_seconds": window_seconds,
            },
        )
    raise HTTPException(
        status_code=429,
        detail="Request limit reached. Wait before starting more AgentOverflow work.",
        headers={
            "Retry-After": str(retry_after),
            "X-RateLimit-Remaining": str(remaining),
        },
    )


async def record_security_event(
    event_type: str,
    actor: str,
    detail: dict | None = None,
) -> None:
    es = get_es()
    if hasattr(es, "record_security_event"):
        await es.record_security_event(event_type, actor_key(actor), detail or {})
