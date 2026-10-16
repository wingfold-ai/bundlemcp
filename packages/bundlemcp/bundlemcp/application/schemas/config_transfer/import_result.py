from pydantic import BaseModel, Field

from bundlemcp.application.schemas.config_transfer.import_outcome import ImportOutcome


class ImportResult(BaseModel):
    """The outcome of importing one resource of the document."""

    kind: str = Field(
        description="What the resource is: 'upstream', 'bundle', 'endpoint', or 'curation' for "
        "one tool's curation in a bundle"
    )
    name: str = Field(
        description="The resource's natural key; a curation is named "
        "'<bundle>/<upstream>/<tool>'"
    )
    outcome: ImportOutcome = Field(
        description="'created', 'updated', 'skipped' when nothing would change, or 'error'"
    )
    message: str | None = Field(
        default=None,
        description="Why the resource errored or was skipped, when it was for a reason other "
        "than being unchanged",
    )
