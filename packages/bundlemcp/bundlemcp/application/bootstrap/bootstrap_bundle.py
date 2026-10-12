from pydantic import ConfigDict, Field

from bundlemcp.application.schemas import BundleUpsert


class BootstrapBundle(BundleUpsert):
    """A bundle in a bootstrap document, with its membership; unknown keys are rejected."""

    model_config = ConfigDict(extra="forbid")  # BOOT-8

    upstreams: list[str] = Field(  # BND-6, BOOT-8
        default=[],
        description="Names of the upstream servers that belong to this bundle",
    )
