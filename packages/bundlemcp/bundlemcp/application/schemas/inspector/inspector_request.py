from pydantic import BaseModel, Field

from bundlemcp.application.schemas.inspector.inspector_target import InspectorTarget


class InspectorRequest(BaseModel):
    """One inspector operation that needs nothing beyond its target."""

    target: InspectorTarget = Field(
        description="What to connect to: a registered upstream, an endpoint of this gateway, or "
        "an ad-hoc URL, selected by 'kind'"
    )
