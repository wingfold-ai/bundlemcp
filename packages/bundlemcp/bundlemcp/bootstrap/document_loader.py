"""Reading a bootstrap YAML file into its validated document."""

from pathlib import Path

import yaml

from bundlemcp.bootstrap.bootstrap_document import BootstrapDocument


def load_document(path: str) -> BootstrapDocument:
    data = yaml.safe_load(Path(path).read_text()) or {}
    return BootstrapDocument(**data)
