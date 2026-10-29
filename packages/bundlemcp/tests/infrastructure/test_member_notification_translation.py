"""The SDK's notifications and listen events, translated once at the pool (PROT-7, PROT-23)."""

import pytest
from bundlemcp.application.contracts.upstream.member_notification import (
    ListedKind,
    MemberListChanged,
    MemberLogMessage,
    MemberResourceUpdated,
)
from bundlemcp.infrastructure.fastmcp.member_notification_translation import (
    from_listen_event,
    from_log_message,
    from_server_notification,
)
from mcp import types
from mcp.shared.subscriptions import (
    PromptsListChanged,
    ResourcesListChanged,
    ResourceUpdated,
    ToolsListChanged,
)

REPORT = "file:///report"
MEMBER_META = {"io.example/trace": "member-hop"}


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (types.ToolListChangedNotification(), MemberListChanged(listed=ListedKind.TOOLS)),
        (types.PromptListChangedNotification(), MemberListChanged(listed=ListedKind.PROMPTS)),
        (
            types.ResourceListChangedNotification(),
            MemberListChanged(listed=ListedKind.RESOURCES),
        ),
        (
            types.ResourceUpdatedNotification(
                params=types.ResourceUpdatedNotificationParams(uri=REPORT, _meta=MEMBER_META)
            ),
            MemberResourceUpdated(uri=REPORT),
        ),
    ],
)
def test_prot23_each_server_notification_maps_to_its_model(message, expected):
    """PROT-23: a handshake-era session's notification becomes its typed model, meta and all
    left behind."""
    assert from_server_notification(message) == expected


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        (ToolsListChanged(), MemberListChanged(listed=ListedKind.TOOLS)),
        (PromptsListChanged(), MemberListChanged(listed=ListedKind.PROMPTS)),
        (ResourcesListChanged(), MemberListChanged(listed=ListedKind.RESOURCES)),
        (ResourceUpdated(uri=REPORT), MemberResourceUpdated(uri=REPORT)),
    ],
)
def test_prot23_each_listen_event_maps_to_its_model(event, expected):
    """PROT-23: a modern member's listen event becomes the same typed model."""
    assert from_listen_event(event) == expected


def test_prot23_an_unknown_sdk_type_maps_to_nothing():
    """PROT-23: a notification the gateway does not act on is not passed on."""
    progress = types.ProgressNotification(
        params=types.ProgressNotificationParams(progress_token="t", progress=1)
    )
    assert from_server_notification(progress) is None
    assert from_server_notification(object()) is None


def test_prot23_an_update_with_an_empty_uri_is_dropped():
    """PROT-23: an update that does not validate is dropped at the pool."""
    message = types.ResourceUpdatedNotification(
        params=types.ResourceUpdatedNotificationParams(uri="")
    )
    assert from_server_notification(message) is None
    assert from_listen_event(ResourceUpdated(uri="")) is None


def test_prot7_a_log_message_keeps_level_logger_and_data_only():
    """PROT-7: the member's own meta stays at the pool."""
    params = types.LoggingMessageNotificationParams(
        level="error", logger="db", data="lost", _meta=MEMBER_META
    )
    assert from_log_message(params) == MemberLogMessage(level="error", logger="db", data="lost")


def test_prot7_a_log_message_that_does_not_validate_is_dropped():
    """PROT-7: data that is not JSON never reaches the router."""
    params = types.LoggingMessageNotificationParams(level="error", data=object())
    assert from_log_message(params) is None
