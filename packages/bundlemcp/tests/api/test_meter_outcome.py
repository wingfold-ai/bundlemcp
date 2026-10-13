"""How a tool call's ending is reported to the metering hook (PROT-26)."""

from types import SimpleNamespace

import pytest
from bundlemcp.api.mcp.tool_call.call_outcome import CANCELLED, UPSTREAM_FAILURE, CallOutcome
from bundlemcp.api.mcp.tool_call.call_status import CallStatus
from bundlemcp.application.metering.meter_outcome import MeterOutcome

RESULT = SimpleNamespace(is_error=False)


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (CallOutcome(status=CallStatus.SUCCESS, result=RESULT), MeterOutcome.RESULT),
        (CallOutcome(status=CallStatus.ERROR, result=RESULT), MeterOutcome.TOOL_ERROR),
        (
            CallOutcome(status=CallStatus.ERROR, error_message="timed out", code=UPSTREAM_FAILURE),
            MeterOutcome.NO_RESULT,
        ),
        (CallOutcome(status=CallStatus.ERROR, error_message="refused"), MeterOutcome.NO_RESULT),
        (
            CallOutcome(status=CallStatus.ERROR, error_message="cancelled", code=CANCELLED),
            MeterOutcome.CANCELLED,
        ),
    ],
)
def test_call_outcome_maps_to_meter_outcome(outcome, expected):
    assert outcome.meter_outcome is expected
