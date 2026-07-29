from __future__ import annotations

import re
from dataclasses import dataclass

from fastapi import HTTPException


@dataclass(frozen=True)
class ContentFinding:
    code: str
    message: str


_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", re.IGNORECASE),
    re.compile(
        r"\b(?:sk_live_|sk_test_|sk-proj-|sk-ant-|ghp_|github_pat_|AKIA)"
        r"[A-Za-z0-9_-]{12,}\b"
    ),
    re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}\b", re.IGNORECASE),
    re.compile(
        r"\b(?:password|passwd|api[_-]?key|secret|token)\s*[:=]\s*[\"']?"
        r"[A-Za-z0-9._~+/=-]{12,}",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:postgres|postgresql|mysql|mongodb(?:\+srv)?|redis)://[^\s]+", re.IGNORECASE),
    re.compile(r"\b(?:AWS_SECRET_ACCESS_KEY|SUPABASE_SERVICE_ROLE_KEY)\s*[:=]", re.IGNORECASE),
)

_PERSONAL_PATH_PATTERNS = (
    re.compile(r"\b[A-Za-z]:\\Users\\[^\\\s]+\\", re.IGNORECASE),
    re.compile(r"(?<![\w/])/(?:home|Users)/[^/\s]+/"),
    re.compile(r"(?<![\w/])/root/"),
    re.compile(r"\\\\[^\\\s]+\\[^\\\s]+\\"),
)

_PROMPT_INJECTION_PATTERNS = (
    re.compile(r"\bignore (?:all |any )?(?:previous|prior|system|developer) instructions?\b", re.IGNORECASE),
    re.compile(r"\b(?:reveal|print|return|expose|dump)\b.{0,60}\b(?:system prompt|developer message|hidden instructions?)\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"\b(?:chain[- ]of[- ]thought|hidden reasoning|internal monologue|private scratchpad)\b", re.IGNORECASE),
    re.compile(r"\b(?:upload|send|post|exfiltrate)\b.{0,80}\b(?:secret|credential|token|api key|environment variable)\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"<\s*script\b", re.IGNORECASE),
    re.compile(r"\bjavascript\s*:", re.IGNORECASE),
)

_BROAD_EXTRACTION_PATTERNS = (
    re.compile(
        r"\b(?:dump|export|scrape|enumerate|download|exfiltrate)\b.{0,80}"
        r"\b(?:all|every|entire|whole|complete)\b.{0,80}"
        r"\b(?:database|dataset|memory|questions?|answers?|records?|reasoning|traces?)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\b(?:show|give|fetch|retrieve|return|list)\b.{0,50}"
        r"\b(?:all|every|entire|whole|complete)\b.{0,50}"
        r"\b(?:questions?|answers?|records?|reasoning|traces?|contents?)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(r"\b(?:page|paginate|cursor)\s*(?:through|over)?\s*(?:all|every|entire)\b", re.IGNORECASE),
    re.compile(r"\b(?:guess|brute[- ]?force|iterate)\b.{0,60}\b(?:ids?|tokens?|questions?|answers?)\b", re.IGNORECASE | re.DOTALL),
)

_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)


def inspect_public_content(text: str, *, reject_email: bool = True) -> list[ContentFinding]:
    value = str(text or "")
    findings: list[ContentFinding] = []

    if any(pattern.search(value) for pattern in _SECRET_PATTERNS):
        findings.append(ContentFinding("credential", "Potential credential or connection secret detected"))
    if any(pattern.search(value) for pattern in _PERSONAL_PATH_PATTERNS):
        findings.append(ContentFinding("personal_path", "Personal filesystem path detected"))
    if any(pattern.search(value) for pattern in _PROMPT_INJECTION_PATTERNS):
        findings.append(ContentFinding("prompt_injection", "Prompt-injection or private-reasoning instruction detected"))
    if reject_email and _EMAIL_PATTERN.search(value):
        findings.append(ContentFinding("email", "Email address detected"))

    return findings


def inspect_search_intent(text: str) -> list[ContentFinding]:
    findings = inspect_public_content(text)
    if any(pattern.search(text or "") for pattern in _BROAD_EXTRACTION_PATTERNS):
        findings.append(ContentFinding("bulk_extraction", "Bulk memory extraction requests are not allowed"))
    return findings


def require_safe_public_content(*values: str, label: str = "content") -> None:
    findings: list[ContentFinding] = []
    for value in values:
        findings.extend(inspect_public_content(value))
    if findings:
        codes = sorted({finding.code for finding in findings})
        raise HTTPException(
            status_code=422,
            detail=f"Unsafe {label} rejected ({', '.join(codes)}). Submit only reusable, non-sensitive technical context.",
        )


def require_safe_search_intent(*values: str) -> None:
    findings: list[ContentFinding] = []
    for value in values:
        findings.extend(inspect_search_intent(value))
    if findings:
        codes = sorted({finding.code for finding in findings})
        raise HTTPException(
            status_code=422,
            detail=f"Search request rejected ({', '.join(codes)}). Submit one genuine, specific engineering subtask.",
        )
