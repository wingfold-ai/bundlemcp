from pydantic import BaseModel


class UpstreamTokens(BaseModel):
    access_token: str
    refresh_token: str | None = None
    expires_in: int | None = None  # seconds
    scope: str | None = None
    account_hint: str | None = None  # e.g. masked account/email for UI (UPO-5)
