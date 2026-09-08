from enum import StrEnum


class EndpointAuthMode(StrEnum):
    OAUTH = "oauth"
    API_KEY = "api_key"
    NONE = "none"
