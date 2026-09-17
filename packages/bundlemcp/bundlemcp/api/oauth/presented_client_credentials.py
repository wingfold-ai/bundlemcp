"""The client credentials a token-endpoint request carries, however it chose to send them."""

from typing import Annotated

from fastapi import Depends, Form, Request

from bundlemcp.domain.oauth.client_credentials import ClientCredentials


def presented_client_credentials(
    request: Request,
    client_id: Annotated[str | None, Form()] = None,
    client_secret: Annotated[str | None, Form()] = None,
) -> ClientCredentials:
    """HTTP Basic wins (client_secret_basic); otherwise the form fields (client_secret_post)."""
    return ClientCredentials.from_basic_header(
        request.headers.get("authorization")
    ) or ClientCredentials(client_id=client_id or "", client_secret=client_secret)


ClientCredentialsProvider = Annotated[ClientCredentials, Depends(presented_client_credentials)]
