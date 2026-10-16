from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.domain.sessions.upstream_failure import UpstreamFailure


class UpstreamRetryPolicy(BaseModel):
    """Whether a request that failed on its upstream session may be sent again, once.

    A request the upstream provably did not run — its session had expired, or
    it never left the gateway — is safe to resend. A read-only request is safe
    to resend after any transport loss, since reading twice changes nothing. A
    tool call whose request reached the upstream may have run, so it is not
    resent. Nothing is resent twice.
    """

    model_config = ConfigDict(frozen=True)

    read_only: bool = Field(
        description="Whether the request only reads, so running it twice is harmless"
    )

    def allows_retry(self, failure: UpstreamFailure | None, *, retried: bool) -> bool:
        if retried or failure is None:
            return False
        if failure in (UpstreamFailure.SESSION_EXPIRED, UpstreamFailure.NOT_SENT):
            return True
        return self.read_only
