from pydantic import ConfigDict, Field

from bundlemcp.application.bootstrap.bootstrap_member import BootstrapMember
from bundlemcp.application.schemas import BundlePromptUpsert, BundleResourceUpsert, BundleUpsert


class BootstrapBundle(BundleUpsert):
    """A bundle in a bootstrap document, with its membership and its own prompts and
    resources; unknown keys are rejected."""

    model_config = ConfigDict(extra="forbid")

    upstreams: list[str | BootstrapMember] = Field(
        default=[],
        description="The bundle's member upstream servers, first member first: a name means "
        "an enabled member, an object also sets its enable flag and its tools' curation. "
        "Members added elsewhere and not named here follow them",
    )
    prompts: list[BundlePromptUpsert] = Field(
        default=[],
        description="Prompts the bundle itself serves, created or replaced by name; a prompt "
        "already stored but not listed here is kept",
    )
    resources: list[BundleResourceUpsert] = Field(
        default=[],
        description="Documents the bundle itself serves, created or replaced by name; a "
        "document already stored but not listed here is kept",
    )

    @property
    def members(self) -> list[BootstrapMember]:
        """Every member in the object form, a bare name meaning enabled with no curation."""
        return [
            BootstrapMember(name=member) if isinstance(member, str) else member
            for member in self.upstreams
        ]
