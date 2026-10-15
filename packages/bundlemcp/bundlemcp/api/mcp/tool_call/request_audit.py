from bundlemcp.api.mcp.protocol.request_context import RequestContext
from bundlemcp.domain.audit.audit_context import AuditContext


def request_audit(ctx: RequestContext, presented_tool_name: str) -> AuditContext:
    """What every audit record of a call on this request says, before the tool is resolved."""
    return AuditContext(
        endpoint_id=ctx.view.endpoint.id,
        endpoint_name=ctx.view.endpoint.name,
        bundle_name=ctx.view.bundle.name,
        presented_tool_name=presented_tool_name,
        user_id=ctx.identity.user_uuid,
        api_key_id=ctx.identity.api_key_uuid,
        auth_method=ctx.identity.auth_method,
        session_id=ctx.routing_key,
    )
