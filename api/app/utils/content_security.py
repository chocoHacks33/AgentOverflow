from __future__ import annotations

import html
import re
import unicodedata
from urllib.parse import unquote
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
    re.compile(
        r"\b(?:call|invoke|use)\b.{0,50}\b(?:tool|plugin|mcp|browser)\b.{0,80}"
        r"\b(?:reveal|export|upload|send|dump|list)\b",
        re.IGNORECASE | re.DOTALL,
    ),
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
_BIDI_OR_ZERO_WIDTH = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060-\u2069\ufeff]")
_LONG_ENCODED_PAYLOAD = re.compile(r"(?:[A-Za-z0-9+/]{160,}={0,2}|(?:%[0-9A-Fa-f]{2}){48,})")
_DESTRUCTIVE_EXECUTION_PATTERNS = (
    re.compile(r"\brm\s+-[a-z]*r[a-z]*f\b\s+(?:/|~|\$HOME)(?:\s|$)", re.IGNORECASE),
    re.compile(r"\bRemove-Item\b.{0,80}\b-Recurse\b.{0,80}(?:[A-Za-z]:\\|\\\\)", re.IGNORECASE | re.DOTALL),
    re.compile(r"\b(?:format|diskpart|mkfs)\b", re.IGNORECASE),
    re.compile(r"\b(?:drop\s+database|truncate\s+(?:table\s+)?agentoverflow_)\b", re.IGNORECASE),
    re.compile(
        r"\b(?:curl|wget|Invoke-WebRequest|Invoke-RestMethod)\b.{0,180}"
        r"(?:\.ssh|id_rsa|\.aws|\.env\b|printenv|environment variables?|credentials?|api[_ -]?keys?|tokens?|secrets?)",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"(?:\$\(|`)\s*(?:cat|type|Get-Content|printenv|env)\b.{0,120}"
        r"\b(?:curl|wget|Invoke-WebRequest|Invoke-RestMethod)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\b(?:curl|wget)\b.{0,220}"
        r"(?:\|\s*(?:sh|bash|zsh|pwsh|powershell)\b|"
        r"(?:-F|--form|--upload-file|-T|--data-binary|--post-file)\b)",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\b(?:Invoke-WebRequest|Invoke-RestMethod)\b.{0,220}\b-InFile\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\b(?:upload|send|post|exfiltrate)\b.{0,100}"
        r"\b(?:repository|source code|workspace|project files?|private files?|build artifacts?)\b",
        re.IGNORECASE | re.DOTALL,
    ),
)


def normalize_for_inspection(text: str) -> str:
    value = unicodedata.normalize("NFKC", str(text or ""))
    for _ in range(3):
        decoded = html.unescape(value)
        try:
            decoded = unquote(decoded)
        except Exception:
            pass
        if decoded == value:
            break
        value = decoded
    value = _BIDI_OR_ZERO_WIDTH.sub("", value)
    value = "".join(char for char in value if char in "\n\r\t" or unicodedata.category(char) != "Cc")
    return value


def inspect_public_content(text: str, *, reject_email: bool = True) -> list[ContentFinding]:
    raw_value = str(text or "")
    value = normalize_for_inspection(raw_value)
    separator_folded = re.sub(r"(?<=\w)[^\w\s]+(?=\w)", "", value)
    findings: list[ContentFinding] = []

    if _BIDI_OR_ZERO_WIDTH.search(raw_value):
        findings.append(ContentFinding("hidden_unicode", "Hidden Unicode controls detected"))
    if _LONG_ENCODED_PAYLOAD.search(value):
        findings.append(ContentFinding("encoded_payload", "Opaque encoded payload detected"))
    if any(pattern.search(value) for pattern in _SECRET_PATTERNS):
        findings.append(ContentFinding("credential", "Potential credential or connection secret detected"))
    if any(pattern.search(value) for pattern in _PERSONAL_PATH_PATTERNS):
        findings.append(ContentFinding("personal_path", "Personal filesystem path detected"))
    if any(
        pattern.search(candidate)
        for pattern in _PROMPT_INJECTION_PATTERNS
        for candidate in (value, separator_folded)
    ):
        findings.append(ContentFinding("prompt_injection", "Prompt-injection or private-reasoning instruction detected"))
    if any(pattern.search(value) for pattern in _DESTRUCTIVE_EXECUTION_PATTERNS):
        findings.append(ContentFinding("unsafe_execution", "Destructive or credential-exfiltrating execution detected"))
    if reject_email and _EMAIL_PATTERN.search(value):
        findings.append(ContentFinding("email", "Email address detected"))

    return findings


def inspect_search_intent(text: str) -> list[ContentFinding]:
    normalized = normalize_for_inspection(text)
    findings = inspect_public_content(normalized)
    separator_folded = re.sub(r"(?<=\w)[^\w\s]+(?=\w)", "", normalized)
    if any(
        pattern.search(candidate)
        for pattern in _BROAD_EXTRACTION_PATTERNS
        for candidate in (normalized, separator_folded)
    ):
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
