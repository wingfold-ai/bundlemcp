"""Reading a bootstrap document, from a file or from an inline string, into its validated model."""

from pathlib import Path

import yaml

from bundlemcp.application.bootstrap.bootstrap_document import BootstrapDocument


def parse_document(text: str) -> BootstrapDocument:
    """Parse YAML or JSON text; JSON is YAML, so one parser serves both sources."""
    data = yaml.safe_load(text) or {}
    return BootstrapDocument.model_validate(data)


def load_document(path: str) -> BootstrapDocument:
    return parse_document(Path(path).read_text())
