from pydantic import Field

from bundlemcp.application.bootstrap.bootstrap_api_key import BootstrapApiKey
from bundlemcp.application.bootstrap.bootstrap_document import BootstrapDocument


class ExportDocument(BootstrapDocument):
    """The document an export writes: a bootstrap document that never carries API keys.

    Keys are identity, not configuration, and only their hashes are stored, so
    the list is left out of what is written rather than shown empty.
    """

    api_keys: list[BootstrapApiKey] = Field(
        default=[],
        exclude=True,
        description="Never set by an export; present so the document stays a bootstrap document",
    )
