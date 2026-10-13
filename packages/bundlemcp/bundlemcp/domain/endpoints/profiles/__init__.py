"""Endpoint profiles: each one a preset implementing one interface, registered in one catalogue."""

from bundlemcp.domain.endpoints.profiles.chatgpt_profile import ChatgptProfile
from bundlemcp.domain.endpoints.profiles.claude_profile import ClaudeProfile
from bundlemcp.domain.endpoints.profiles.default_profile import DefaultProfile
from bundlemcp.domain.endpoints.profiles.endpoint_profile_preset import EndpointProfilePreset
from bundlemcp.domain.endpoints.profiles.profile_catalog import ProfileCatalog
from bundlemcp.domain.endpoints.profiles.profile_rule_violation import ProfileRuleViolation

__all__ = [
    "ChatgptProfile",
    "ClaudeProfile",
    "DefaultProfile",
    "EndpointProfilePreset",
    "ProfileCatalog",
    "ProfileRuleViolation",
]
