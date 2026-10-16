"""Secret-token helpers: generate, hash, compare.

One-way handling, as opposed to the reversible cipher in ``token_cipher``:
only hashes are stored, and comparisons run on hashes with constant-time
equality.
"""

import hashlib
import hmac
import re
import secrets

API_KEY_PREFIX = "bmcp_sk_"
ACCESS_TOKEN_PREFIX = "bmcp_at_"
REFRESH_TOKEN_PREFIX = "bmcp_rt_"
DELEGATED_TOKEN_PREFIX = "bmcp_dt_"
# what a key value supplied from outside must look like: the prefix and a urlsafe secret
API_KEY_FORMAT = re.compile(r"^bmcp_sk_[A-Za-z0-9_-]{32,}$")


def generate_token(prefix: str) -> str:
    return prefix + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def tokens_equal(hash_a: str, hash_b: str) -> bool:
    return hmac.compare_digest(hash_a, hash_b)


def display_prefix(token: str, keep: int = 12) -> str:
    return token[:keep] + "…"
