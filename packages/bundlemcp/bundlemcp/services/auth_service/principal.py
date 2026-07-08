from dataclasses import dataclass


@dataclass
class Principal:
    """The authenticated management-API caller: an admin user or a service key."""

    kind: str  # "admin" | "service"
    user_id: str | None = None
    api_key_id: str | None = None
