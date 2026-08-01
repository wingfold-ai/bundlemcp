"""Dump the management-API OpenAPI document to stdout.

Used as a build step by the web app to generate its TypeScript client types:

    uv run python -m bundlemcp.api.export_openapi > apps/web/openapi.json
"""

import json
import sys

from bundlemcp.api.app import create_app
from bundlemcp.settings import Settings


def main() -> None:
    app = create_app(Settings(database_url="postgresql+asyncpg://x:x@localhost/x"))
    json.dump(app.openapi(), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
