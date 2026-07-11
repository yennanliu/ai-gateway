"""Lightweight PII detection + redaction (regex heuristics, v1)."""

from __future__ import annotations

import re

_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "phone": re.compile(r"\b(?:\+?\d{1,3}[ -]?)?(?:\(?\d{3}\)?[ -]?)\d{3}[ -]?\d{4}\b"),
}


def scan(text: str) -> list[str]:
    """Return the sorted kinds of PII found in text."""
    return sorted(kind for kind, pat in _PATTERNS.items() if pat.search(text))


def redact(text: str) -> str:
    """Replace detected PII with ``[REDACTED:<kind>]`` tokens."""
    result = text
    # SSN before credit_card/phone so the more specific pattern wins.
    for kind in ("email", "ssn", "credit_card", "phone"):
        result = _PATTERNS[kind].sub(f"[REDACTED:{kind}]", result)
    return result
