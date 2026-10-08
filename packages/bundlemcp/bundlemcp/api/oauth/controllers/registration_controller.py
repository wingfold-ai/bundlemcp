"""Dynamic Client Registration (RFC 7591)."""

from fastapi import Request

from bundlemcp.api.http.client_ip import client_ip
from bundlemcp.api.http.controller import Controller
from bundlemcp.api.http.providers import SettingsProvider
from bundlemcp.api.http.route import route
from bundlemcp.api.oauth.providers import ClientRegistrationServiceProvider
from bundlemcp.api.oauth.registration_body import RegistrationBodyProvider
from bundlemcp.application.schemas import ClientRegistrationResponse


class ClientRegistrationController(Controller):
    prefix = "/oauth"
    tags = ("oauth",)
    include_in_schema = False

    # a public client gets no client_secret field at all, not a null one
    @route.post("/register", status_code=201, response_model_exclude_none=True)
    async def register_client(
        self,
        body: RegistrationBodyProvider,
        request: Request,
        service: ClientRegistrationServiceProvider,
        settings: SettingsProvider,
    ) -> ClientRegistrationResponse:
        # OAS-12: per client IP, which behind a trusted proxy is the forwarded one
        return await service.register(body, client_ip(request, settings))
