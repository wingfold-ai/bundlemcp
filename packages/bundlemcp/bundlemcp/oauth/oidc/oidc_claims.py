from pydantic import BaseModel


class OidcClaims(BaseModel):
    issuer: str
    sub: str
    email: str | None = None
    name: str | None = None
    groups: list[str] = []
