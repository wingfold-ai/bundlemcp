from pydantic import BaseModel, Field

from bundlemcp.domain.bundles.resource_mime_type import ResourceMimeType
from bundlemcp.domain.shared.resource_names import BundleResourceName


class BundleResourceUpsert(BaseModel):
    """Body for creating or replacing a document the bundle itself serves.

    Not secret: the document is served to every caller of every endpoint of the
    bundle, and to the model.
    """

    name: BundleResourceName = Field(  # BPR-6
        description="Resource name, unique in the bundle; '/' separates folders, as in "
        "'guides/style'. Clients read it as bundle://resources/<name>"
    )
    title: str | None = Field(default=None, description="Human-readable title")
    description: str | None = Field(
        default=None, description="What the document contains, shown in a client's list"
    )
    mime_type: ResourceMimeType = Field(
        default=ResourceMimeType.MARKDOWN, description="Text format of the content"
    )
    content: str = Field(  # BPR-16, BPR-17
        description="The document itself, at most 256 KiB, and at most 4 MiB across the "
        "bundle's resources. Not secret: served to every caller of the bundle and to the model"
    )
