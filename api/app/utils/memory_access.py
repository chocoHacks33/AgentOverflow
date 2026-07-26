from __future__ import annotations

import base64
import hashlib
import hmac
import time

from fastapi import HTTPException

from app.config import settings


def _secret() -> bytes:
    configured = settings.agentoverflow_access_secret.strip()
    if configured:
        return configured.encode("utf-8")
    fallback = settings.supabase_database_url or settings.elasticsearch_api_key
    if fallback:
        return hashlib.sha256(fallback.encode("utf-8")).digest()
    return b"agentoverflow-local-dev-access-secret"


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def create_question_access_token(question_id: str, user_id: str) -> str:
    expires_at = int(time.time()) + settings.memory_answer_token_seconds
    payload = f"q:{question_id}:{user_id}:{expires_at}"
    sig = hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).digest()
    return f"{_b64(payload.encode('utf-8'))}.{_b64(sig)}"


def verify_question_access_token(token: str | None, question_id: str, user_id: str) -> None:
    if not token:
        raise HTTPException(status_code=403, detail="Question access token required")
    try:
        encoded_payload, encoded_sig = token.split(".", 1)
        payload = _unb64(encoded_payload).decode("utf-8")
        supplied_sig = _unb64(encoded_sig)
        expected_sig = hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).digest()
    except Exception as exc:
        raise HTTPException(status_code=403, detail="Invalid question access token") from exc

    if not hmac.compare_digest(supplied_sig, expected_sig):
        raise HTTPException(status_code=403, detail="Invalid question access token")

    try:
        scope, token_question_id, token_user_id, expires_at = payload.split(":", 3)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Invalid question access token") from exc

    if scope != "q" or token_question_id != question_id or token_user_id != user_id:
        raise HTTPException(status_code=403, detail="Question access token does not match request")
    if int(expires_at) < int(time.time()):
        raise HTTPException(status_code=403, detail="Question access token expired")


def memory_reads_protected() -> bool:
    return settings.protected_memory_reads
