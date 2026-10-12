"""Reading a bootstrap document, from a file or from an inline string, into its validated model."""

from pathlib import Path

import structlog
import yaml

from bundlemcp.application.bootstrap.bootstrap_document import BootstrapDocument
from bundlemcp.application.bootstrap.servers_key_rename import FORMER_KEY, KEY, former_key_uses

log = structlog.get_logger(__name__)


def parse_document(text: str) -> BootstrapDocument:
    """Parse YAML or JSON text; JSON is YAML, so one parser serves both sources."""
    data = yaml.safe_load(text) or {}
    uses = former_key_uses(data)
    if uses:  # BOOT-8: one warning per document, naming every place to change
        log.warning("bootstrap.former_key", former=FORMER_KEY, key=KEY, where=uses)
    return BootstrapDocument.model_validate(data)


def load_document(path: str) -> BootstrapDocument:
    return parse_document(Path(path).read_text())
