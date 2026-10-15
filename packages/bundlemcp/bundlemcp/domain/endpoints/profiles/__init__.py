"""Endpoint profiles: each one a preset implementing one interface, registered in one catalogue."""

from bundlemcp.domain.endpoints.profiles.default_profile import DefaultProfile
from bundlemcp.domain.endpoints.profiles.endpoint_profile_preset import EndpointProfilePreset
from bundlemcp.domain.endpoints.profiles.oauth_only_profile import OauthOnlyProfile
from bundlemcp.domain.endpoints.profiles.profile_catalog import ProfileCatalog
from bundlemcp.domain.endpoints.profiles.profile_rule_violation import ProfileRuleViolation
from bundlemcp.domain.endpoints.profiles.write_as_read_profile import WriteAsReadProfile

__all__ = [
    "DefaultProfile",
    "EndpointProfilePreset",
    "OauthOnlyProfile",
    "ProfileCatalog",
    "ProfileRuleViolation",
    "WriteAsReadProfile",
]
