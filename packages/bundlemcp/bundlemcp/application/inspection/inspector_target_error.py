from bundlemcp.application.errors.service_error import ServiceError
from bundlemcp.application.schemas.inspector.inspector_failure import InspectorFailure


class InspectorTargetError(ServiceError):
    """The inspector's target gave no usable answer to the operation.

    ``report`` is set when the target gave no MCP answer at all, classified;
    a target that answered with a JSON-RPC error has none.
    """

    status = 502

    def __init__(self, message: str, report: InspectorFailure | None = None) -> None:
        self.report = report
        super().__init__(message)
