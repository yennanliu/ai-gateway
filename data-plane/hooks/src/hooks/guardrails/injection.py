"""Prompt-injection heuristic (v1: keyword/phrase patterns)."""

from __future__ import annotations

import re

_PATTERNS = [
    re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions", re.I),
    re.compile(r"disregard\s+(?:the\s+)?(?:previous|prior|system)\b", re.I),
    re.compile(r"reveal\s+(?:your\s+)?(?:system\s+prompt|instructions)", re.I),
    re.compile(r"you\s+are\s+now\s+(?:a|an|in)\b", re.I),
    re.compile(r"\bDAN\b|do\s+anything\s+now", re.I),
]


def detect(text: str) -> bool:
    """True if the text looks like a prompt-injection attempt."""
    return any(pat.search(text) for pat in _PATTERNS)
