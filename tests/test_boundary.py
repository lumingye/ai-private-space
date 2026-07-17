from reference.boundary import GatewayBoundary, PrivacyMode, notice_for


def test_gateway_filters_private_event():
    boundary = GatewayBoundary(PrivacyMode.GATEWAY)
    event = {"tool_name": "private_open", "result": {"content": "secret"}, "private": True}
    assert boundary.forward_event(event) is None


def test_gateway_forwards_public_event():
    boundary = GatewayBoundary(PrivacyMode.GATEWAY)
    event = {"tool_name": "weather", "result": {"temp": 20}}
    assert boundary.forward_event(event) == event


def test_soft_notice_is_explicit():
    notice = notice_for(PrivacyMode.SOFT)
    assert notice.tool_trace_visible is True
    assert notice.sensitive_content_allowed is False
    assert "软隐私" in notice.message
