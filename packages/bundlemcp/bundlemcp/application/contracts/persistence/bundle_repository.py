from typing import Protocol, runtime_checkable

from bundlemcp.application.contracts.persistence.repository import NamedRepository
from bundlemcp.domain.bundles.bundle import Bundle


@runtime_checkable
class BundleRepository(NamedRepository[Bundle], Protocol):
    """Bundles, the units servers are composed into."""
