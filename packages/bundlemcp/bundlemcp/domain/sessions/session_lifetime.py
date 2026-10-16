from pydantic import BaseModel, ConfigDict, Field

# how often the session sweeper runs; the store keeps a record this much longer than its
# lifetime, twice over, so the sweeper normally expires it with its bindings in hand
SWEEP_INTERVAL_SECONDS = 60


class SessionLifetime(BaseModel):
    """How long a handshake-era session lives without activity."""

    model_config = ConfigDict(frozen=True)

    seconds: int = Field(ge=0, description="Idle seconds before the session expires; 0 for never")

    @property
    def expires(self) -> bool:
        return self.seconds > 0

    @property
    def store_ttl(self) -> int:
        """The record's TTL in the store: the lifetime plus the sweeper's margin.

        The sweeper expires a session once its lifetime has passed; the TTL is
        the backstop that removes it when no sweeper runs.
        """
        return self.seconds + 2 * SWEEP_INTERVAL_SECONDS
