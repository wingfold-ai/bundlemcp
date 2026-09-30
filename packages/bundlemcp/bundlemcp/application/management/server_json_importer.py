"""Drafting a registration from an MCP Registry server.json document."""

import re
from typing import Any

from bundlemcp.application.schemas import ServerJsonDraft, ServerJsonHeader
from bundlemcp.domain.servers.server_name_suggestion import suggest_server_name

STREAMABLE_HTTP = "streamable-http"
_URL_VARIABLE = re.compile(r"\{([A-Za-z0-9_.-]+)\}")


class ServerJsonImporter:
    """Reads the parts of a server.json the gateway can use; fetches and stores nothing.

    Only ``remotes`` matter: packages describe local installs the gateway
    cannot run. The first streamable-http remote is taken, with the headers
    its publisher declared, so the credential form can be drawn from them.
    """

    def draft(self, document: dict[str, Any]) -> ServerJsonDraft:
        problems: list[str] = []
        remotes = [r for r in document.get("remotes") or [] if isinstance(r, dict)]
        usable = [r for r in remotes if r.get("type") == STREAMABLE_HTTP and r.get("url")]
        if not remotes:
            problems.append("The document lists no remote: the server only runs locally.")
        elif not usable:
            kinds = sorted({str(r.get("type")) for r in remotes})
            problems.append(
                f"No streamable-http remote (found: {', '.join(kinds)}); the gateway only "
                "speaks Streamable HTTP."
            )
        remote = usable[0] if usable else {}
        url = remote.get("url")
        return ServerJsonDraft(
            name=suggest_server_name(document.get("name"), url or ""),
            description=document.get("description"),
            url=url,
            url_variables=list(dict.fromkeys(_URL_VARIABLE.findall(url or ""))),
            headers=[
                ServerJsonHeader(
                    name=header["name"],
                    description=header.get("description"),
                    is_required=bool(header.get("isRequired", False)),
                    is_secret=bool(header.get("isSecret", False)),
                    value=header.get("value"),
                )
                for header in remote.get("headers") or []
                if isinstance(header, dict) and header.get("name")
            ],
            website_url=document.get("websiteUrl"),
            problems=problems,
        )
