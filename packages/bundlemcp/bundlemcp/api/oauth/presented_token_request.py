"""The grant parameters a token-endpoint request carries (RFC 6749 sections 4.1.3 and 6)."""

from typing import Annotated

from fastapi import Depends, Form

from bundlemcp.api.http.providers import SettingsProvider
from bundlemcp.application.oauth_server import TokenRequest
from bundlemcp.domain.endpoints.endpoint_resource import EndpointResource


def presented_token_request(
    settings: SettingsProvider,
    grant_type: Annotated[str, Form()],
    code: Annotated[str | None, Form()] = None,
    redirect_uri: Annotated[str | None, Form()] = None,
    code_verifier: Annotated[str | None, Form()] = None,
    refresh_token: Annotated[str | None, Form()] = None,
    resource: Annotated[str | None, Form()] = None,
) -> TokenRequest:
    """Collect the form fields every grant may send into the one object a grant reads.

    Each grant uses a different subset — the code grant sends ``code``,
    ``redirect_uri`` and ``code_verifier``, the refresh grant sends
    ``refresh_token`` — so the endpoint accepts the union and lets the grant
    named by ``grant_type`` refuse what it is missing. Declaring the fields
    here keeps them out of every handler signature, and documents the endpoint
    in the OpenAPI schema in one place. ``resource`` (RFC 8707) is read into
    the endpoint it names here, where the public URL is known.
    """
    named = EndpointResource.parse(settings.public_base, resource) if resource else None
    return TokenRequest(
        resource=resource,
        resource_endpoint=named.endpoint_name if named else None,
        grant_type=grant_type,
        code=code,
        redirect_uri=redirect_uri,
        code_verifier=code_verifier,
        refresh_token=refresh_token,
    )


TokenRequestProvider = Annotated[TokenRequest, Depends(presented_token_request)]
