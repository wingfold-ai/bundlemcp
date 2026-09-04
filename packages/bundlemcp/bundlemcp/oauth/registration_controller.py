"""Dynamic Client Registration (RFC 7591), rate-limited per IP."""

from fastapi import HTTPException, Request

from bundlemcp.http import Controller, route
from bundlemcp.oauth.providers import ClientRegistrationServiceProvider, RateLimiterProvider
from bundlemcp.schemas import ClientRegistrationRequest, ClientRegistrationResponse

REGISTRATION_RATE_LIMIT = 10  # per window
REGISTRATION_RATE_WINDOW = 3600  # seconds


class ClientRegistrationController(Controller):
    prefix = "/oauth"
    tags = ("oauth",)
    include_in_schema = False

    # a public client gets no client_secret field at all, not a null one
    @route.post("/register", status_code=201, response_model_exclude_none=True)
    async def register_client(
        self,
        body: ClientRegistrationRequest,
        request: Request,
        service: ClientRegistrationServiceProvider,
        rate_limiter: RateLimiterProvider,
    ) -> ClientRegistrationResponse:
        ip = request.client.host if request.client else "unknown"
        result = await rate_limiter.check(
            f"dcr:{ip}", REGISTRATION_RATE_LIMIT, REGISTRATION_RATE_WINDOW
        )
        if not result.allowed:
            raise HTTPException(429, {"error": "rate_limited"})
        return await service.register(body)
