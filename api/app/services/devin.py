from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config import settings


@dataclass
class DevinSession:
    session_id: str | None
    url: str | None
    status: str | None
    raw: dict[str, Any]


class DevinUnavailable(RuntimeError):
    pass


def devin_enabled() -> bool:
    return bool(settings.devin_api_key and settings.devin_org_id)


def create_devin_session(
    *,
    prompt: str,
    title: str,
    repo: str | None,
) -> DevinSession:
    if not devin_enabled():
        raise DevinUnavailable("DEVIN_API_KEY and DEVIN_ORG_ID are required to create a Devin session")

    base_url = settings.devin_base_url.rstrip("/")
    url = f"{base_url}/v3/organizations/{settings.devin_org_id}/sessions"
    payload: dict[str, Any] = {
        "prompt": prompt,
        "title": title[:180],
        "tags": ["agentoverflow", "escalation"],
        "devin_mode": settings.devin_mode,
        "max_acu_limit": settings.devin_max_acu_limit,
        "structured_output_required": False,
    }
    if repo:
        payload["repos"] = [repo]

    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.devin_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Devin API returned {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach Devin API: {exc.reason}") from exc

    return DevinSession(
        session_id=data.get("session_id"),
        url=data.get("url"),
        status=data.get("status"),
        raw=data,
    )
