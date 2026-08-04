"""Constants for admin browser sessions."""

SESSION_COOKIE = "bmcp_session"
ADMIN_SESSION_KEY = "bmcp:adminsession:{session_id}"
DEFAULT_MAX_AGE = 12 * 3600  # seconds; forces re-login (ADM-6)
