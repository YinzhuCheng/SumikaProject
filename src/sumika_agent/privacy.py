from __future__ import annotations

import re
from dataclasses import dataclass


SENSITIVE_MARKER = "[已隐去敏感信息]"

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("token", re.compile(r"(?i)\b(?:token|api[_-]?key|authorization|cookie)\s*[:=]\s*[^\s,;]+")),
    ("password", re.compile(r"(?i)\b(?:password|passwd|pwd|密码)\s*[:=：]\s*[^\s,;]+")),
    ("phone", re.compile(r"(?<!\d)(?:\+?86[-\s]?)?1[3-9]\d{9}(?!\d)")),
    ("id_card", re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")),
    ("bank_card", re.compile(r"(?<!\d)(?:\d[ -]?){15,19}\d(?!\d)")),
)

_SENSITIVE_KEYWORDS = (
    "身份证",
    "住址",
    "家庭地址",
    "银行卡",
    "验证码",
    "密码",
    "token",
    "cookie",
    "authorization",
    "api key",
)


@dataclass(frozen=True)
class RedactionResult:
    text: str
    redacted: bool
    labels: tuple[str, ...]


def redact_sensitive(text: str) -> RedactionResult:
    """Redact secrets and high-risk personal identifiers before memory ingestion."""

    redacted = text
    labels: list[str] = []
    for label, pattern in _PATTERNS:
        if pattern.search(redacted):
            labels.append(label)
            redacted = pattern.sub(SENSITIVE_MARKER, redacted)
    return RedactionResult(redacted, bool(labels), tuple(sorted(set(labels))))


def looks_sensitive(text: str) -> bool:
    lowered = text.lower()
    if any(keyword in lowered for keyword in _SENSITIVE_KEYWORDS):
        return True
    return redact_sensitive(text).redacted
