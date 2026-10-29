"""Drafting a registration from an MCP Registry server.json document."""

import re
from typing import Any

from bundlemcp.application.management.server_json.registry_server_document import (
    RegistryServerDocument,
)
from bundlemcp.application.schemas import ServerJsonDraft, ServerJsonHeader
from bundlemcp.domain.servers.server_name_suggestion import suggest_server_name

_URL_VARIABLE = re.compile(r"\{([A-Za-z0-9_.-]+)\}")


class ServerJsonImporter:
    """Reads the parts of a server.json the gateway can use; fetches and stores nothing.

    Only ``remotes`` matter: packages describe local installs the gateway
    cannot run. The first streamable-http remote is taken, with the headers
    its publisher declared, so the credential form can be drawn from them.
    """

    def draft(self, document: dict[str, Any]) -> ServerJsonDraft:
        server = RegistryServerDocument.model_validate(document)
        remote = server.first_usable_remote
        problems: list[str] = []
        if not server.remotes:
            problems.append("The document lists no remote: the server only runs locally.")
        elif remote is None:
            kinds = sorted({str(r.type) for r in server.remotes})
            problems.append(
                f"No streamable-http remote (found: {', '.join(kinds)}); the gateway only "
                "speaks Streamable HTTP."
            )
        url = remote.url if remote is not None else None
        return ServerJsonDraft(
            name=suggest_server_name(server.name, url or ""),
            description=server.description,
            url=url,
            url_variables=list(dict.fromkeys(_URL_VARIABLE.findall(url or ""))),
            headers=[
                ServerJsonHeader(
                    name=header.name,
                    description=header.description,
                    is_required=header.is_required,
                    is_secret=header.is_secret,
                    value=header.value,
                )
                for header in (remote.headers if remote is not None else [])
                if header.name
            ],
            website_url=server.website_url,
            problems=problems,
        )
