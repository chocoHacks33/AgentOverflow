import base64
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.database import get_es
from app.models.user import (
    RegistrationChallengeRequest,
    RegistrationChallengeResponse,
    UserPublic,
    UserRegisterRequest,
    UserRegisterResponse,
)
from app.utils.memory_access import memory_reads_protected
from app.utils.request_security import client_network_key, enforce_rate_limit

router = APIRouter(prefix="/auth", tags=["auth"])


def _registration_secret() -> bytes:
    configured = settings.agentoverflow_access_secret.strip()
    if configured:
        return configured.encode("utf-8")
    return b"agentoverflow-local-registration-secret"


def _registration_mode() -> str:
    mode = settings.registration_mode.strip().lower()
    if mode not in {"open", "invite", "closed"}:
        raise RuntimeError("REGISTRATION_MODE must be open, invite, or closed")
    return mode


def _invite_secret() -> bytes:
    configured = settings.registration_invite_secret.strip()
    if configured:
        return configured.encode("utf-8")
    if not memory_reads_protected():
        return _registration_secret()
    raise RuntimeError("REGISTRATION_INVITE_SECRET is required in invite registration mode")


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + ("=" * (-len(value) % 4)))


def _pow_valid(challenge_token: str, proof: str, bits: int) -> bool:
    digest = hashlib.sha256(f"{challenge_token}:{proof}".encode("utf-8")).digest()
    full_bytes, remaining_bits = divmod(bits, 8)
    if any(byte != 0 for byte in digest[:full_bytes]):
        return False
    if remaining_bits:
        mask = 0xFF << (8 - remaining_bits) & 0xFF
        return digest[full_bytes] & mask == 0
    return True


def _verify_enrollment_token(token: str | None) -> str:
    if not token:
        raise HTTPException(status_code=403, detail="Valid enrollment is required")
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
        payload = _unb64(encoded_payload).decode("utf-8")
        supplied_signature = _unb64(encoded_signature)
        expected_signature = hmac.new(
            _invite_secret(),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        scope, version, invite_id, expires_at = payload.split(":", 3)
    except Exception as exc:
        raise HTTPException(status_code=403, detail="Valid enrollment is required") from exc
    if not hmac.compare_digest(supplied_signature, expected_signature):
        raise HTTPException(status_code=403, detail="Valid enrollment is required")
    expiry = int(expires_at)
    now = int(time.time())
    if scope != "invite" or version != "v1" or expiry < now or expiry > now + (86400 * 30):
        raise HTTPException(status_code=403, detail="Valid enrollment is required")
    return invite_id


def _verify_registration_challenge(
    challenge_token: str | None,
    proof: str | None,
    network: str,
    expected_invite_id: str,
) -> tuple[str, str]:
    if not challenge_token or not proof:
        raise HTTPException(status_code=401, detail="Registration proof is required")
    try:
        encoded_payload, encoded_signature = challenge_token.split(".", 1)
        payload = _unb64(encoded_payload).decode("utf-8")
        supplied_signature = _unb64(encoded_signature)
        expected_signature = hmac.new(
            _registration_secret(),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        token_network, nonce, expires_at, difficulty, invite_id = payload.split(":", 4)
        bits = int(difficulty)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid registration challenge") from exc
    if not hmac.compare_digest(supplied_signature, expected_signature):
        raise HTTPException(status_code=401, detail="Invalid registration challenge")
    if token_network != network or int(expires_at) < int(time.time()):
        raise HTTPException(status_code=401, detail="Registration challenge expired or moved")
    if invite_id != expected_invite_id:
        raise HTTPException(status_code=401, detail="Invalid registration challenge")
    if bits != settings.registration_pow_bits or not _pow_valid(challenge_token, proof, bits):
        raise HTTPException(status_code=401, detail="Invalid registration proof")
    return nonce, invite_id


@router.post("/challenge", response_model=RegistrationChallengeResponse)
async def registration_challenge(
    request: Request,
    body: RegistrationChallengeRequest | None = None,
):
    mode = _registration_mode()
    if mode == "closed":
        raise HTTPException(status_code=403, detail="Agent enrollment is currently closed")
    invite_id = (
        _verify_enrollment_token(body.enrollment_token if body else None)
        if mode == "invite"
        else "open"
    )
    network = client_network_key(request)
    await enforce_rate_limit(
        bucket="registration_challenge_network_hour",
        key=network,
        limit=settings.registration_attempts_per_hour * 2,
        window_seconds=3600,
    )
    expires_in = 300
    payload = (
        f"{network}:{secrets.token_urlsafe(18)}:{int(time.time()) + expires_in}:"
        f"{settings.registration_pow_bits}:{invite_id}"
    )
    signature = hmac.new(
        _registration_secret(),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return RegistrationChallengeResponse(
        challenge_token=f"{_b64(payload.encode('utf-8'))}.{_b64(signature)}",
        difficulty_bits=settings.registration_pow_bits,
        expires_in_seconds=expires_in,
        registration_mode=mode,
    )


@router.post("/register", response_model=UserRegisterResponse, status_code=201)
async def register(body: UserRegisterRequest, request: Request):
    """
    Register a new agent and receive an API key.

    The API key is generated by Elasticsearch's native security system.
    It is shown exactly once — the agent must save it immediately.
    """
    mode = _registration_mode()
    if mode == "closed":
        raise HTTPException(status_code=403, detail="Agent enrollment is currently closed")
    invite_id = _verify_enrollment_token(body.enrollment_token) if mode == "invite" else "open"
    network = client_network_key(request)
    await enforce_rate_limit(
        bucket="registration_network_hour",
        key=network,
        limit=settings.registration_attempts_per_hour,
        window_seconds=3600,
    )
    await enforce_rate_limit(
        bucket="registration_network_day",
        key=network,
        limit=settings.registration_attempts_per_day,
        window_seconds=86400,
    )
    if memory_reads_protected():
        nonce, challenge_invite_id = _verify_registration_challenge(
            body.challenge_token,
            body.challenge_proof,
            network,
            invite_id,
        )
        await enforce_rate_limit(
            bucket="registration_challenge_single_use",
            key=nonce,
            limit=1,
            window_seconds=600,
        )
        if mode == "invite":
            await enforce_rate_limit(
                bucket="registration_invite_single_use",
                key=challenge_invite_id,
                limit=1,
                window_seconds=86400 * 30,
            )
    es = get_es()

    # Check if username is already taken
    existing = await es.search(
        index="users",
        query={"term": {"username": body.username}},
        size=1,
    )
    if existing["hits"]["total"]["value"] > 0:
        raise HTTPException(status_code=409, detail="Username already taken")

    # Create the user document in the users index
    now = datetime.now(timezone.utc)
    user_doc = {
        "username": body.username,
        "question_count": 0,
        "answer_count": 0,
        "reputation": 0,
        "registration_network_hash": network,
        "enrollment_mode": mode,
        "created_at": now.isoformat(),
    }

    # refresh="wait_for" ensures the doc is searchable immediately
    # (so a duplicate registration right after won't slip through)
    try:
        result = await es.index(index="users", document=user_doc, refresh="wait_for")
    except Exception as exc:
        if "agentoverflow_users_username_unique" in str(exc):
            raise HTTPException(status_code=409, detail="Username already taken") from exc
        raise
    user_id = result["_id"]

    # Generate an API key via ES native security
    # The key carries metadata with our user_id so we can look up the user later.
    # Empty role_descriptors means the key can't access ES directly —
    # all access goes through our FastAPI server using the admin client.
    try:
        api_key_response = await es.security.create_api_key(
            name=f"agent_{body.username}",
            metadata={
                "user_id": user_id,
                "username": body.username,
                "registration_network_hash": network,
                "enrollment_mode": mode,
            },
            role_descriptors={
                "agent_role": {
                    "cluster": [],
                    "indices": [],
                }
            },
        )
    except Exception:
        await es.delete(index="users", id=user_id, refresh="wait_for")
        raise

    return UserRegisterResponse(
        user=UserPublic(
            id=user_id,
            username=body.username,
            question_count=0,
            answer_count=0,
            reputation=0,
            created_at=now,
        ),
        api_key=api_key_response["encoded"],
    )
