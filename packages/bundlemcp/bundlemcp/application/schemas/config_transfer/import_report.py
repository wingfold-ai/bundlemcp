from pydantic import BaseModel, Field

from bundlemcp.application.schemas.config_transfer.import_result import ImportResult


class ImportReport(BaseModel):
    """What an import did, resource by resource."""

    dry_run: bool = Field(description="Whether this was a dry run that wrote nothing by design")
    applied: bool = Field(
        description="Whether the document was written: false on a dry run, and whenever any "
        "resource errored, since a document lands entirely or not at all"
    )
    results: list[ImportResult] = Field(
        description="One result per resource of the document, in the order they were applied"
    )

    @property
    def errors(self) -> list[ImportResult]:
        return [result for result in self.results if result.outcome == "error"]
