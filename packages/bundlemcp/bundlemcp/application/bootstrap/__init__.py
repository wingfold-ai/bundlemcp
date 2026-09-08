"""Idempotent startup provisioning.

Applies a declarative config document as upserts by natural key, reusing the
same domain rules as the management API. Runs in-process at startup; failures
honor BOOTSTRAP_STRICT.
"""

from bundlemcp.application.bootstrap.bootstrap_bundle import BootstrapBundle
from bundlemcp.application.bootstrap.bootstrap_document import BootstrapDocument
from bundlemcp.application.bootstrap.bootstrap_runner import BootstrapRunner
from bundlemcp.application.bootstrap.document_loader import load_document, parse_document

__all__ = [
    "BootstrapBundle",
    "BootstrapDocument",
    "BootstrapRunner",
    "load_document",
    "parse_document",
]
