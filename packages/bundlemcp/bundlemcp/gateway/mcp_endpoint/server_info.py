from typing import Any

SERVER_VERSION = "0.1.0"


def server_info(bundle_name: str) -> dict[str, Any]:
    """How the gateway names itself to a client of one bundle."""
    return {"name": f"bundlemcp/{bundle_name}", "version": SERVER_VERSION}
