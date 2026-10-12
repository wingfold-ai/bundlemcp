from typing import Any

from pydantic import Field, model_validator

from bundlemcp.application.bootstrap.servers_key_rename import accept_former_key
from bundlemcp.application.schemas import BundleUpsert


class BootstrapBundle(BundleUpsert):
    """A bundle in a bootstrap document, with its membership."""

    upstreams: list[str] = Field(  # BND-6, BOOT-8
        default=[],
        description="Names of the upstream servers that belong to this bundle. The former key "
        "'servers' is still accepted",
    )

    @model_validator(mode="before")
    @classmethod
    def _accept_former_key(cls, data: Any) -> Any:
        return accept_former_key(data)
