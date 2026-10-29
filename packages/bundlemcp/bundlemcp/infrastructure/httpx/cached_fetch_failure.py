from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.application.errors import InvalidInputError


class FetchFailureKind(StrEnum):
    """Why a client metadata document could not be used."""

    UNREACHABLE = "unreachable"
    INVALID = "invalid"


class CachedFetchFailure(BaseModel):
    """A failed metadata-document fetch, remembered so the same URL is not fetched again at once."""

    model_config = ConfigDict(frozen=True)

    kind: FetchFailureKind = Field(description="Whether the document was unreachable or invalid")

    def error(self) -> InvalidInputError:
        """The error a fresh fetch failing this way raises, so a cached failure reads the same."""
        if self.kind is FetchFailureKind.INVALID:
            return InvalidInputError("client metadata document is invalid")
        return InvalidInputError("client metadata document could not be fetched")
