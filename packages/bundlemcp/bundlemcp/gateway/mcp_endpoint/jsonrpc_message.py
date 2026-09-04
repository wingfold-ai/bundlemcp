"""One JSON-RPC message as the MCP client sent it."""

from typing import Any

from pydantic import BaseModel, Field, field_validator


class JsonRpcMessage(BaseModel):
    """A request, notification or response from the client, parsed once at the edge.

    A request carries a method and an id; a notification a method and no id; a
    response no method but a result or error, answering a request the gateway
    relayed to the client earlier.
    """

    id: int | str | None = Field(
        default=None, description="Correlation id; absent on notifications"
    )
    method: str | None = Field(default=None, description="Method name; absent on a response")
    params: dict[str, Any] = Field(default_factory=dict, description="Method parameters")
    result: Any = Field(default=None, description="Payload of a successful response")
    error: dict[str, Any] | None = Field(default=None, description="Payload of a failed response")

    @field_validator("params", mode="before")
    @classmethod
    def _none_is_empty(cls, value: Any) -> Any:
        return {} if value is None else value

    @classmethod
    def parse(cls, body: Any) -> "JsonRpcMessage":
        if not isinstance(body, dict):
            raise ValueError("a JSON-RPC message is an object")
        return cls.model_validate(body)

    @property
    def is_response(self) -> bool:
        return self.method is None and bool({"result", "error"} & self.model_fields_set)

    @property
    def is_notification(self) -> bool:
        return self.method is not None and self.method.startswith("notifications/")

    @property
    def progress_token(self) -> Any:
        return (self.params.get("_meta") or {}).get("progressToken")

    def param(self, key: str, default: Any = None) -> Any:
        value = self.params.get(key)
        return default if value is None else value

    def body(self) -> dict[str, Any]:
        """The message as sent, for relaying a client response onward unchanged."""
        return self.model_dump(exclude_unset=True)
