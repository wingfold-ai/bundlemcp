"""Bundle composition: presented tool surface + call routing.

Pipeline order: curation filter -> overrides -> profile transform.
"""

from bundlemcp.gateway.composition.aggregate_capabilities import aggregate_capabilities
from bundlemcp.gateway.composition.bundle_view import BundleView
from bundlemcp.gateway.composition.bundle_view_loader import load_bundle_view
from bundlemcp.gateway.composition.presented_tool import PREFIX_SEP, PresentedTool

__all__ = [
    "PREFIX_SEP",
    "BundleView",
    "PresentedTool",
    "aggregate_capabilities",
    "load_bundle_view",
]
