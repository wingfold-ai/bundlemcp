"""Secret-token helpers (KEY-1, OAS-8, DOM-3): generate, hash, compare.

Only hashes are stored; comparisons run on hashes with constant-time equality.
"""

import hashlib
import hmac
import secrets

API_KEY_PREFIX = "bmcp_sk_"  # KEY-1
ACCESS_TOKEN_PREFIX = "bmcp_at_"  # OAS-4
REFRESH_TOKEN_PREFIX = "bmcp_rt_"


def generate_token(prefix: str) -> str:
    return prefix + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def tokens_equal(hash_a: str, hash_b: str) -> bool:
    return hmac.compare_digest(hash_a, hash_b)


def display_prefix(token: str, keep: int = 12) -> str:
    return token[:keep] + "…"
