"""Runtime-tunable configuration: ConfigEntry over typed defaults.

Values are cached per replica; the cache participates in STP invalidation
(entity_type="config"), so a PUT on any replica takes effect everywhere
within the propagation-latency budget — never TTL-based.

The key registry itself (``DEFAULTS``, ``coerce``, ``UnknownConfigKey``) is
owned by ``bundlemcp.services.config_service`` and re-exported here for
gateway-side consumers.
"""

from bundlemcp.gateway.runtime_config.runtime_config import RuntimeConfig
from bundlemcp.services.config_service import DEFAULTS, UnknownConfigKey, coerce

__all__ = ["DEFAULTS", "RuntimeConfig", "UnknownConfigKey", "coerce"]
