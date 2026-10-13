from pydantic import BaseModel, ConfigDict, Field, model_validator

from bundlemcp.domain.endpoints.endpoint_profile import EndpointProfile
from bundlemcp.domain.endpoints.profiles.chatgpt_profile import ChatgptProfile
from bundlemcp.domain.endpoints.profiles.claude_profile import ClaudeProfile
from bundlemcp.domain.endpoints.profiles.default_profile import DefaultProfile
from bundlemcp.domain.endpoints.profiles.endpoint_profile_preset import EndpointProfilePreset


class ProfileCatalog(BaseModel):
    """The single place a profile is registered.

    Adding a profile means one ``EndpointProfile`` member, one preset class and
    one entry here; a catalogue must cover every member, so a half-registered
    profile fails at construction rather than on the first request that uses it.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    presets: dict[EndpointProfile, EndpointProfilePreset] = Field(
        description="Each profile's preset, keyed by the identifier endpoints store"
    )

    @model_validator(mode="after")
    def every_profile_registered_under_its_name(self) -> "ProfileCatalog":
        missing = [p.value for p in EndpointProfile if p not in self.presets]
        if missing:
            raise ValueError(f"profiles without a preset: {missing}")
        for key, preset in self.presets.items():
            if preset.name != key:
                raise ValueError(f"preset {preset.name} registered as {key}")
        return self

    @classmethod
    def builtin(cls) -> "ProfileCatalog":
        """The profiles the gateway ships."""
        presets: list[EndpointProfilePreset] = [DefaultProfile(), ClaudeProfile(), ChatgptProfile()]
        return cls(presets={p.name: p for p in presets})

    def get(self, profile: EndpointProfile) -> EndpointProfilePreset:
        return self.presets[profile]

    def all(self) -> list[EndpointProfilePreset]:
        """Every registered profile, in the order the identifiers are declared."""
        return [self.presets[p] for p in EndpointProfile]
