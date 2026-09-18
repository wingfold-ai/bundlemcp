"""The client credentials a token-endpoint request carries, however it chose to send them."""

from typing import Annotated

from fastapi import Depends, Form, Request

from bundlemcp.domain.oauth.client_credentials import ClientCredentials


def presented_client_credentials(
    request: Request,
    client_id: Annotated[str | None, Form()] = None,
    client_secret: Annotated[str | None, Form()] = None,
) -> ClientCredentials:
    """Read the client's credentials from either place RFC 6749 allows it to put them.

    A client may authenticate with an HTTP Basic header
    (``client_secret_basic``) or with form fields (``client_secret_post``), and
    a public client sends only its identifier. Resolving that here means each
    handler asks for one ``ClientCredentials`` instead of repeating the
    header-versus-form rule. Basic wins when both are present, as RFC 6749
    section 2.3.1 prefers it.
    """
    return ClientCredentials.from_basic_header(
        request.headers.get("authorization")
    ) or ClientCredentials(client_id=client_id or "", client_secret=client_secret)


ClientCredentialsProvider = Annotated[ClientCredentials, Depends(presented_client_credentials)]
