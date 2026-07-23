"""Shared constants and logger for OIDC relying-party login."""

import structlog

log = structlog.get_logger("bundlemcp.oauth.oidc")

OIDC_STATE_KEY = "bmcp:oidcstate:{state}"
OIDC_STATE_TTL = 600
