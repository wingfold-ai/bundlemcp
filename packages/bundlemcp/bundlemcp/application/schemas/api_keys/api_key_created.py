from pydantic import Field

from bundlemcp.application.schemas.api_keys.api_key_read import ApiKeyRead


class ApiKeyCreated(ApiKeyRead):
    """A newly created key, including the secret."""

    key: str = Field(  # KEY-1
        description="The secret value. Returned only in this response and never again, "
        "so store it now",
    )
