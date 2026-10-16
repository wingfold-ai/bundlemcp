from typing import Annotated

from pydantic import Field

from bundlemcp.application.schemas.inspector.inspector_call_outcome import InspectorCallOutcome
from bundlemcp.application.schemas.inspector.inspector_failure import InspectorFailure
from bundlemcp.application.schemas.inspector.inspector_progress import InspectorProgress

InspectorCallEvent = Annotated[
    InspectorProgress | InspectorCallOutcome | InspectorFailure, Field(discriminator="type")
]
