"""Endpoint profiles as registered presets (EP-14, EP-15)."""

import pytest
from bundlemcp.domain.endpoints.endpoint_auth_mode import EndpointAuthMode
from bundlemcp.domain.endpoints.endpoint_profile import EndpointProfile
from bundlemcp.domain.endpoints.profiles import (
    ChatgptProfile,
    ClaudeProfile,
    DefaultProfile,
    EndpointProfilePreset,
    ProfileCatalog,
    ProfileRuleViolation,
)
from pydantic import ValidationError

OAUTH = EndpointAuthMode.OAUTH
API_KEY = EndpointAuthMode.API_KEY
NONE = EndpointAuthMode.NONE


def test_ep14_catalog_matches_enum():
    """Every stored profile identifier has exactly one preset, registered under its own name."""
    catalog = ProfileCatalog.builtin()
    assert [p.name for p in catalog.all()] == list(EndpointProfile)
    assert all(isinstance(p, EndpointProfilePreset) for p in catalog.all())


def test_ep14_a_half_registered_catalog_is_refused():
    with pytest.raises(ValidationError, match="profiles without a preset"):
        ProfileCatalog(presets={EndpointProfile.DEFAULT: DefaultProfile()})


def test_ep14_a_preset_registered_under_another_name_is_refused():
    with pytest.raises(ValidationError, match="registered as"):
        ProfileCatalog(
            presets={
                EndpointProfile.DEFAULT: ClaudeProfile(),
                EndpointProfile.CLAUDE: ClaudeProfile(),
                EndpointProfile.CHATGPT: ChatgptProfile(),
            }
        )


@pytest.mark.parametrize(
    "modes", [{OAUTH}, {API_KEY}, {NONE}, {OAUTH, API_KEY}], ids=["oauth", "key", "none", "both"]
)
def test_ep15_default_auth_rule_accepts_any_mode(modes):
    DefaultProfile().check_auth_modes(frozenset(modes))


def test_ep15_claude_auth_rule_requires_oauth_alone():
    ClaudeProfile().check_auth_modes(frozenset({OAUTH}))
    for modes in ({API_KEY}, {OAUTH, API_KEY}, {NONE}):
        with pytest.raises(ProfileRuleViolation, match="claude profile"):
            ClaudeProfile().check_auth_modes(frozenset(modes))


def test_ep15_chatgpt_auth_rule_requires_oauth_or_api_key():
    for modes in ({OAUTH}, {API_KEY}, {OAUTH, API_KEY}):
        ChatgptProfile().check_auth_modes(frozenset(modes))
    with pytest.raises(ProfileRuleViolation, match="chatgpt profile"):
        ChatgptProfile().check_auth_modes(frozenset({NONE}))


def test_ep14_listing_fields_come_from_the_presets():
    catalog = ProfileCatalog.builtin()
    assert catalog.get(EndpointProfile.CHATGPT).warning
    assert catalog.get(EndpointProfile.DEFAULT).warning is None
    assert all(p.description for p in catalog.all())
