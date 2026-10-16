from pydantic import BaseModel, Field


class CheckResult(BaseModel):
    """One readiness check: passed, or failed with a short reason."""

    ok: bool = Field(description="Whether the check passed")
    reason: str | None = Field(default=None, description="Why it failed, without secrets")


class ReadinessReport(BaseModel):
    """What a replica needs before it should receive traffic, one check at a time."""

    postgres: CheckResult = Field(description="The durable store answers")
    valkey: CheckResult = Field(description="The live store answers")
    migrations: CheckResult = Field(
        description="The database schema is at or past the migration head this release ships"
    )

    @property
    def failing(self) -> list[str]:
        """The names of the checks that failed, in a fixed order."""
        checks = {"postgres": self.postgres, "valkey": self.valkey, "migrations": self.migrations}
        return [name for name, check in checks.items() if not check.ok]

    @property
    def ready(self) -> bool:
        return not self.failing
