from pydantic import Field

from bundlemcp.schemas import BundleUpsert


class BootstrapBundle(BundleUpsert):
    """A bundle in a bootstrap document, with its membership."""

    servers: list[str] = Field(  # BND-6
        default=[],
        description="Names of the servers that belong to this bundle",
    )
