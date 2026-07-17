"""Privacy-mode declarations and gateway event filtering."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class PrivacyMode(str, Enum):
    SOFT = "soft_privacy"
    GATEWAY = "gateway_isolated"


PRIVATE_TOOL_NAMES = {
    "private_create",
    "private_open",
    "private_due_list",
    "private_share",
    "private_trash",
    "private_destroy",
}


@dataclass(frozen=True)
class PrivacyNotice:
    mode: PrivacyMode
    tool_trace_visible: bool
    sensitive_content_allowed: bool

    @property
    def message(self) -> str:
        if self.mode is PrivacyMode.SOFT:
            return (
                "当前为软隐私模式：内容不会进入普通记忆或自动召回，"
                "但宿主前端可能显示工具名称、参数和返回结果。"
                "请勿存入必须对前端使用者保密的内容。"
            )
        return (
            "当前为 gateway 前端隔离模式：私人工具事件不会下发到浏览器。"
            "这不等于 VPS 管理员或模型供应商不可访问运行时明文。"
        )


class GatewayBoundary:
    """Filter internal private-tool events before any browser transport."""

    def __init__(self, mode: PrivacyMode):
        self.mode = mode

    def forward_event(self, event: dict[str, Any]) -> dict[str, Any] | None:
        tool_name = str(event.get("tool_name") or "")
        is_private = tool_name in PRIVATE_TOOL_NAMES or bool(event.get("private"))
        if self.mode is PrivacyMode.GATEWAY and is_private:
            return None
        return event

    def safe_log_record(self, event: dict[str, Any]) -> dict[str, Any]:
        tool_name = str(event.get("tool_name") or "")
        is_private = tool_name in PRIVATE_TOOL_NAMES or bool(event.get("private"))
        if not is_private:
            return event
        return {
            "event_id": event.get("event_id"),
            "tool_name": tool_name,
            "status": event.get("status", "unknown"),
            "private": True,
            "arguments_redacted": True,
            "result_redacted": True,
        }


def notice_for(mode: PrivacyMode) -> PrivacyNotice:
    if mode is PrivacyMode.SOFT:
        return PrivacyNotice(mode, tool_trace_visible=True, sensitive_content_allowed=False)
    return PrivacyNotice(mode, tool_trace_visible=False, sensitive_content_allowed=False)
