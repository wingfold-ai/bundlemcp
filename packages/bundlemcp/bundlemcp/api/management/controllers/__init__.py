"""The management API, one controller per resource; mounted under the API prefix."""

from bundlemcp.api.management.controllers.api_key_controller import ApiKeyController
from bundlemcp.api.management.controllers.audit_controller import AuditController
from bundlemcp.api.management.controllers.bundle_controller import BundleController
from bundlemcp.api.management.controllers.bundle_prompt_controller import BundlePromptController
from bundlemcp.api.management.controllers.bundle_resource_controller import (
    BundleResourceController,
)
from bundlemcp.api.management.controllers.config_controller import ConfigController
from bundlemcp.api.management.controllers.config_transfer_controller import (
    ConfigTransferController,
)
from bundlemcp.api.management.controllers.endpoint_controller import EndpointController
from bundlemcp.api.management.controllers.inspector_controller import InspectorController
from bundlemcp.api.management.controllers.live_log_controller import LiveLogController
from bundlemcp.api.management.controllers.management_controller import ManagementController
from bundlemcp.api.management.controllers.me_controller import MeController
from bundlemcp.api.management.controllers.member_curation_controller import (
    MemberCurationController,
)
from bundlemcp.api.management.controllers.server_controller import ServerController
from bundlemcp.api.management.controllers.user_controller import UserController

__all__ = [
    "ApiKeyController",
    "AuditController",
    "BundleController",
    "BundlePromptController",
    "BundleResourceController",
    "ConfigController",
    "ConfigTransferController",
    "EndpointController",
    "InspectorController",
    "LiveLogController",
    "ManagementController",
    "MeController",
    "MemberCurationController",
    "ServerController",
    "UserController",
]
