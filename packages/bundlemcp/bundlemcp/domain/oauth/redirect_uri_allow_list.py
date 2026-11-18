"""The redirect URIs an operator lets OAuth clients of this gateway use."""

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.domain.oauth.redirect_uri_pattern import RedirectUriPattern


class RedirectUriAllowList(BaseModel):
    """The operator's allow-list of redirect URIs; an empty list leaves every URI open.

    It narrows, and never widens, the scheme rule every redirect URI must pass
    anyway: a URI on the list that is not https (or http on localhost) is still
    refused.
    """

    model_config = ConfigDict(frozen=True)

    patterns: tuple[RedirectUriPattern, ...] = Field(
        default=(),
        description="Exact URIs and wildcard-host entries a redirect URI may match",
    )

    @classmethod
    def of(cls, entries: Iterable[str]) -> RedirectUriAllowList:
        """Parse configured entries; a malformed one raises a validation error naming it."""
        return cls(patterns=tuple(RedirectUriPattern(pattern=entry) for entry in entries))

    @property
    def is_restricted(self) -> bool:
        """Whether the operator configured any entry, so URIs outside it are refused."""
        return bool(self.patterns)

    def permits(self, uri: str) -> bool:
        """Whether a client may use this redirect URI: always while the list is empty."""
        return not self.is_restricted or self._listed(uri)

    def vouches_for(self, uris: Iterable[str]) -> bool:
        """Whether the operator explicitly listed every one of these URIs.

        An empty list vouches for nothing: leaving every URI open is not the
        same as trusting them.
        """
        listed = [self._listed(uri) for uri in uris]
        return self.is_restricted and bool(listed) and all(listed)

    def _listed(self, uri: str) -> bool:
        return any(pattern.matches(uri) for pattern in self.patterns)
