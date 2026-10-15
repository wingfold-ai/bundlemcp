from importlib.metadata import version
from typing import Any

SERVER_VERSION = version("bundlemcp")


def server_info(bundle_name: str) -> dict[str, Any]:
    """How the gateway names itself to a client of one bundle."""
    return {"name": f"bundlemcp/{bundle_name}", "version": SERVER_VERSION}
