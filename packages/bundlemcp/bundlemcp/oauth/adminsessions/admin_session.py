from dataclasses import dataclass


@dataclass
class AdminSession:
    user_id: str
    email: str | None
    is_admin: bool
