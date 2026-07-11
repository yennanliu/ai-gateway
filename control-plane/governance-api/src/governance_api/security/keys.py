"""Virtual-key generation and hashing.

Keys are high-entropy random tokens, so a fast SHA-256 is sufficient (no need
for a slow password hash). Only the hash and a display prefix are stored; the
plaintext is shown to the caller exactly once at issue/rotate time.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

KEY_PREFIX = "sk-ag-"
_DISPLAY_LEN = len(KEY_PREFIX) + 8


def generate_key() -> tuple[str, str, str]:
    """Return (plaintext, display_prefix, hashed_key)."""
    plaintext = f"{KEY_PREFIX}{secrets.token_urlsafe(32)}"
    return plaintext, key_prefix(plaintext), hash_key(plaintext)


def key_prefix(plaintext: str) -> str:
    """Non-secret, human-identifiable prefix (e.g. ``sk-ag-AbCd1234``)."""
    return plaintext[:_DISPLAY_LEN]


def hash_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()


def verify_key(plaintext: str, hashed: str) -> bool:
    """Constant-time comparison used by the data-plane custom-auth hook (M3)."""
    return hmac.compare_digest(hash_key(plaintext), hashed)
