import json

import pytest

from reference.boundary import (
    PRIVATE_TOOL_NAMES,
    GatewayBoundary,
    PrivacyMode,
    notice_for,
    validate_transport_settings,
)


def test_gateway_filters_private_event():
    boundary = GatewayBoundary(PrivacyMode.GATEWAY)
    event = {
        "tool_name": "private_open",
        "result": {"content": "secret"},
        "private": True,
    }
    assert boundary.forward_event(event) is None


def test_string_mode_is_coerced_before_filtering():
    boundary = GatewayBoundary("gateway_isolated")
    event = {"tool_name": "private_open", "result": {"content": "secret"}}
    assert boundary.mode is PrivacyMode.GATEWAY
    assert boundary.forward_event(event) is None
    notice = notice_for("gateway_isolated")
    assert notice.mode is PrivacyMode.GATEWAY
    assert notice.tool_trace_visible is False


@pytest.mark.parametrize("tool_name", sorted(PRIVATE_TOOL_NAMES))
def test_all_documented_private_tools_are_filtered_when_namespaced(tool_name):
    boundary = GatewayBoundary(PrivacyMode.GATEWAY)
    event = {"type": "tool_result", "tool_name": f"mcp__vault__{tool_name}"}
    assert boundary.forward_event(event) is None


def test_unknown_tool_event_fails_closed():
    boundary = GatewayBoundary(PrivacyMode.GATEWAY)
    event = {
        "type": "tool_result",
        "tool_name": "new_tool_not_yet_classified",
        "result": {"content": "secret"},
    }
    assert boundary.forward_event(event) is None


def test_registered_public_tool_is_forwarded():
    boundary = GatewayBoundary(
        PrivacyMode.GATEWAY,
        public_tool_names={"weather"},
    )
    event = {"type": "tool_result", "tool_name": "weather", "result": {"temp": 20}}
    assert boundary.forward_event(event) == event


def test_event_payload_cannot_declassify_unknown_tool_as_public():
    boundary = GatewayBoundary(PrivacyMode.GATEWAY)
    event = {
        "type": "tool_result",
        "tool_name": "weather",
        "private": False,
        "result": {"temp": 20},
    }
    assert boundary.forward_event(event) is None


def test_private_tool_cannot_be_registered_public():
    with pytest.raises(ValueError):
        GatewayBoundary(
            PrivacyMode.GATEWAY,
            public_tool_names={"private_open"},
        )


def test_safe_log_record_does_not_copy_error_details_or_tool_name():
    boundary = GatewayBoundary(PrivacyMode.GATEWAY)
    event = {
        "event_id": "evt-safe-1",
        "tool_name": "private_open",
        "status": "failed: content=MARKER",
        "arguments": {"content": "MARKER"},
        "result": {"content": "MARKER"},
    }
    record = boundary.safe_log_record(event)
    serialized = json.dumps(record)
    assert "MARKER" not in serialized
    assert "private_open" not in serialized
    assert record["status"] == "unknown"
    assert record["arguments_redacted"] is True
    assert record["result_redacted"] is True


def test_gateway_transport_configuration_rejects_client_exposure():
    with pytest.raises(ValueError):
        validate_transport_settings(
            "gateway_isolated",
            expose_private_tools_to_client=True,
            stream_private_tool_events=False,
        )
    with pytest.raises(ValueError):
        validate_transport_settings(
            "gateway_isolated",
            expose_private_tools_to_client=False,
            stream_private_tool_events=True,
        )
    assert (
        validate_transport_settings(
            "gateway_isolated",
            expose_private_tools_to_client=False,
            stream_private_tool_events=False,
        )
        is PrivacyMode.GATEWAY
    )


def test_private_log_configuration_is_always_rejected():
    with pytest.raises(ValueError):
        validate_transport_settings(
            "soft_privacy",
            expose_private_tools_to_client=True,
            stream_private_tool_events=True,
            log_private_results=True,
        )


def test_soft_mode_forwards_but_warns_about_tool_trace():
    event = {"tool_name": "private_open", "result": {"content": "secret"}}
    assert GatewayBoundary(PrivacyMode.SOFT).forward_event(event) == event
    assert notice_for(PrivacyMode.SOFT).tool_trace_visible is True
