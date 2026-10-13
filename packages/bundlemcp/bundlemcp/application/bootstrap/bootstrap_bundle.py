from pydantic import ConfigDict, Field

from bundlemcp.application.schemas import BundlePromptUpsert, BundleResourceUpsert, BundleUpsert


class BootstrapBundle(BundleUpsert):
    """A bundle in a bootstrap document, with its membership and its own prompts and
    resources; unknown keys are rejected."""

    model_config = ConfigDict(extra="forbid")  # BOOT-8

    upstreams: list[str] = Field(  # BND-6, BOOT-8
        default=[],
        description="Names of the upstream servers that belong to this bundle",
    )
    prompts: list[BundlePromptUpsert] = Field(  # BPR-15
        default=[],
        description="Prompts the bundle itself serves, created or replaced by name; a prompt "
        "already stored but not listed here is kept",
    )
    resources: list[BundleResourceUpsert] = Field(  # BPR-15
        default=[],
        description="Documents the bundle itself serves, created or replaced by name; a "
        "document already stored but not listed here is kept",
    )
