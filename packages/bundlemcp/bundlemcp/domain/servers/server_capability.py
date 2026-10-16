from enum import StrEnum


class ServerCapability(StrEnum):
    """A capability an upstream advertises at initialize, keyed as in its capabilities object.

    Only the ones the gateway reaches members for live are listed; tools are
    served from the discovery cache instead.
    """

    PROMPTS = "prompts"
    RESOURCES = "resources"
    COMPLETIONS = "completions"
    LOGGING = "logging"
