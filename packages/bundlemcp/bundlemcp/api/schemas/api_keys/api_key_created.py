from bundlemcp.api.schemas.api_keys.api_key_read import ApiKeyRead


class ApiKeyCreated(ApiKeyRead):
    key: str  # KEY-1: shown exactly once
