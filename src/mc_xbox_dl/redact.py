"""Redaction and masking of sensitive credentials for logs, diagnostics, and --debug mode."""

import re
from typing import Any

SENSITIVE_KEYS: set[str] = {
    "access_token",
    "refresh_token",
    "xsts_token",
    "token",
    "authorization",
    "rpsticket",
    "code",
    "user_code",
    "device_code",
    "ticket",
    "client_secret",
    "usertokens",
    "usertoken",
}

# Regular expressions detecting common authentication patterns and tokens
RE_BEARER = re.compile(r"(Bearer\s+)[A-Za-z0-9\-_.]+", re.IGNORECASE)
RE_XBL_AUTH = re.compile(r"(XBL3\.0\s+x=)[^;]+;[^\s]+", re.IGNORECASE)
RE_RPS_TICKET = re.compile(r"\b([td]=)[A-Za-z0-9\-_.]+", re.IGNORECASE)
RE_JWT = re.compile(r"eyJ[A-Za-z0-9\-_]+(?:\.[A-Za-z0-9\-_]+){2,4}")

RE_KEY_VALUE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in SENSITIVE_KEYS) + r")=([^&\s\"\'<>]+)",
    re.IGNORECASE,
)


def redact_string(val: str) -> str:
    """Applies redaction regex filters to a string."""
    redacted = RE_KEY_VALUE.sub(r"\1=***", val)
    redacted = RE_BEARER.sub(r"\1***", redacted)
    redacted = RE_XBL_AUTH.sub(r"\1***;***", redacted)
    redacted = RE_RPS_TICKET.sub(r"\1***", redacted)
    redacted = RE_JWT.sub("***JWT***", redacted)
    return redacted


def redact_data(obj: Any) -> Any:
    """
    Recursively traverses dictionaries, lists, and strings masking sensitive values.
    Returns a new copy without modifying the original data structure.
    """
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            k_lower = str(k).lower()
            if k_lower in SENSITIVE_KEYS:
                result[k] = "***"
            else:
                result[k] = redact_data(v)
        return result

    if isinstance(obj, list):
        return [redact_data(item) for item in obj]

    if isinstance(obj, tuple):
        return tuple(redact_data(item) for item in obj)

    if isinstance(obj, str):
        return redact_string(obj)

    return obj
