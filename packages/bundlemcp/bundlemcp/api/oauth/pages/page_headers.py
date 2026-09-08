"""Hardening headers for the browser-facing auth pages."""

# SEC-6
PAGE_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'",
    "X-Frame-Options": "DENY",
    "Cache-Control": "no-store",
}
