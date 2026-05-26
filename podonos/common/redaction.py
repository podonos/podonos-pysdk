"""Utilities for redacting secrets from logs, exceptions, and local state."""

from __future__ import annotations

import re
from typing import Any

_REDACTED = "[REDACTED]"

_SIGNED_URL_RE = re.compile(r"(https?://[^\s?]+)\?[^\s)\]}>]+")
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b("
    r"x-api-key|api[_-]?key|authorization|bearer|token|access[_-]?token|"
    r"password|passwd|client[_-]?secret|refresh[_-]?token|id[_-]?token|"
    r"secret[_-]?key|private[_-]?key|session[_-]?token|oauth[_-]?token|"
    r"x-amz-signature|x-amz-credential|x-amz-security-token|signature|credential|"
    r"cloudfront-signature|cloudfront-policy|cloudfront-key-pair-id|"
    r"cookie|set-cookie"
    r")\b\s*[:=]\s*[^\s,&)\]}>]+"
)
_QUOTED_SECRET_FIELD_RE = re.compile(
    r"(?i)(['\"](?:"
    r"x-api-key|api[_-]?key|authorization|bearer|token|access[_-]?token|"
    r"password|passwd|client[_-]?secret|refresh[_-]?token|id[_-]?token|"
    r"secret[_-]?key|private[_-]?key|session[_-]?token|oauth[_-]?token|"
    r"x-amz-signature|x-amz-credential|x-amz-security-token|signature|credential|"
    r"cloudfront-signature|cloudfront-policy|cloudfront-key-pair-id|"
    r"cookie|set-cookie"
    r")['\"]\s*:\s*)['\"][^'\"]+['\"]"
)
_BEARER_VALUE_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+\-/]+=*")
_QUERY_SECRET_RE = re.compile(
    r"(?i)([?&](?:X-Amz-Signature|X-Amz-Credential|X-Amz-Security-Token|"
    r"Signature|Credential|token|access_token|refresh_token|id_token|"
    r"api_key|api-key|password|client_secret|secret_key|private_key|"
    r"CloudFront-Signature|CloudFront-Policy|CloudFront-Key-Pair-Id)=)[^\s&#)\]}>]+"
)


def redact_secrets(value: Any) -> str:
    """Return a string with common API keys, bearer tokens, and signed URLs redacted."""

    text = str(value)
    text = _SIGNED_URL_RE.sub(r"\1?[REDACTED]", text)
    text = _QUERY_SECRET_RE.sub(lambda match: f"{match.group(1)}{_REDACTED}", text)
    text = _QUOTED_SECRET_FIELD_RE.sub(
        lambda match: f"{match.group(1)}'{_REDACTED}'", text
    )
    text = _BEARER_VALUE_RE.sub(f"Bearer {_REDACTED}", text)
    text = _SECRET_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}={_REDACTED}", text)
    return text


def mask_secret(value: str, *, visible_prefix: int = 4, visible_suffix: int = 2) -> str:
    """Mask a single secret for exceptional cases where identity hint is useful."""

    if not value:
        return _REDACTED
    if len(value) <= visible_prefix + visible_suffix:
        return _REDACTED
    return f"{value[:visible_prefix]}...{value[-visible_suffix:]}"
