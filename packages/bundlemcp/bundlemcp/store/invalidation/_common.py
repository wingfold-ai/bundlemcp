from typing import Literal

from bundlemcp.store.redis import INVALIDATION_CHANNEL

EntityType = Literal["server", "bundle", "bundle_tool", "endpoint", "api_key", "config"]

__all__ = ["INVALIDATION_CHANNEL", "EntityType"]
