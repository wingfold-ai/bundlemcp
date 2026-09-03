"""Idempotent startup provisioning.

Applies a declarative config document as upserts by natural key, reusing the
same domain rules as the management API. Runs in-process at startup; failures
honor BOOTSTRAP_STRICT.
"""

from bundlemcp.bootstrap.bootstrap_bundle import BootstrapBundle
from bundlemcp.bootstrap.bootstrap_document import BootstrapDocument
from bundlemcp.bootstrap.bootstrap_runner import apply_document, run_bootstrap
from bundlemcp.bootstrap.bootstrap_server import BootstrapServer
from bundlemcp.bootstrap.document_loader import load_document

__all__ = [
    "BootstrapBundle",
    "BootstrapDocument",
    "BootstrapServer",
    "apply_document",
    "load_document",
    "run_bootstrap",
]
