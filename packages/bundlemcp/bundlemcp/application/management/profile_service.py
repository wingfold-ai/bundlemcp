"""The endpoint profiles an admin can choose, as the management API lists them."""

from bundlemcp.application.schemas import EndpointProfileRead
from bundlemcp.domain.endpoints.profiles.profile_catalog import ProfileCatalog


class ProfileService:
    def __init__(self, profiles: ProfileCatalog) -> None:
        self._profiles = profiles

    def list(self) -> list[EndpointProfileRead]:
        """Every registered profile, so the UI never hard-codes one."""
        return [
            EndpointProfileRead(name=p.name, description=p.description, warning=p.warning)
            for p in self._profiles.all()
        ]
