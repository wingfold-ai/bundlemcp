"""The management API, one controller per resource; mounted under the API prefix."""

from bundlemcp.api.controllers.api_key_controller import ApiKeyController
from bundlemcp.api.controllers.audit_controller import AuditController
from bundlemcp.api.controllers.bundle_controller import BundleController
from bundlemcp.api.controllers.config_controller import ConfigController
from bundlemcp.api.controllers.endpoint_controller import EndpointController
from bundlemcp.api.controllers.health_controller import HealthController
from bundlemcp.api.controllers.management_controller import ManagementController
from bundlemcp.api.controllers.me_controller import MeController
from bundlemcp.api.controllers.server_controller import ServerController
from bundlemcp.api.controllers.user_controller import UserController

__all__ = [
    "ApiKeyController",
    "AuditController",
    "BundleController",
    "ConfigController",
    "EndpointController",
    "HealthController",
    "ManagementController",
    "MeController",
    "ServerController",
    "UserController",
]
