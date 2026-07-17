"""Privacy modes and fail-closed gateway event filtering.

This module is intentionally framework-independent. A real gateway must call
``forward_event`` before every browser transport and must register public tool
events in ``public_tool_names``. Event payloads cannot declassify a tool by
claiming that it is public.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable


class PrivacyMode(str, Enum):
    SOFT = "soft_privacy"
    GATEWAY = "gateway_isolated"


class EventSensitivity(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    UNKNOWN_TOOL = "unknown_tool"


PRIVATE_TOOL_NAMES = frozenset(
    {
        "private_anchor",
        "private_due_list",
        "private_create",
        "private_open",
        "private_update",
        "private_share",
        "private_trash",
        "private_restore",
        "private_destroy",
        "private_accept_inbox",
    }
)

_SAFE_EVENT_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z")
_STATUS_ALIASES = {
    "ok": "ok",
    "success": "ok",
    "succeeded": "ok",
    "error": "error",
    "failed": "error",
    "failure": "error",
    "cancelled": "cancelled",
    "canceled": "cancelled",
    "timeout": "timeout",
    "timed_out": "timeout",
}


def _name_candidates(value: Any) -> frozenset[str]:
    """Return defensive candidates for plain and namespaced tool names."""
    if not isinstance(value, str):
        return frozenset()
    text = value.strip()
    if not text:
        return frozenset()
    candidates = {text}
    for separator in ("__", "/", ":", "."):
        if separator in text:
            candidates.add(text.rsplit(separator, 1)[-1])
    return frozenset(candidates)


def _tool_name_candidates(event: dict[str, Any]) -> frozenset[str]:
    candidates: set[str] = set()
    for key in ("tool_name", "function_name"):
        candidates.update(_name_candidates(event.get(key)))

    for key in ("tool", "function", "tool_call", "function_call"):
        nested = event.get(key)
        if isinstance(nested, str):
            candidates.update(_name_candidates(nested))
        elif isinstance(nested, dict):
            for nested_key in ("name", "tool_name", "function_name"):
                candidates.update(_name_candidates(nested.get(nested_key)))
    return frozenset(candidates)


def _looks_like_tool_event(event: dict[str, Any], names: frozenset[str]) -> bool:
    if names:
        return True
    if any(key in event for key in ("tool_call", "function_call", "tool_result")):
        return True
    event_kind = " ".join(
        str(event.get(key) or "").lower() for key in ("type", "event", "kind")
    )
    return "tool" in event_kind or "function" in event_kind


def _explicit_sensitivity(event: dict[str, Any]) -> EventSensitivity | None:
    for key in ("sensitivity", "visibility", "classification"):
        value = event.get(key)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"private", "secret", "internal_private"}:
                return EventSensitivity.PRIVATE

    marker = event.get("private")
    if marker is True:
        return EventSensitivity.PRIVATE
    if isinstance(marker, str):
        normalized = marker.strip().lower()
        if normalized in {"true", "private"}:
            return EventSensitivity.PRIVATE
    return None


def _safe_status(value: Any) -> str:
    if not isinstance(value, str):
        return "unknown"
    return _STATUS_ALIASES.get(value.strip().lower(), "unknown")


def _safe_event_id(value: Any) -> str | None:
    if isinstance(value, str) and _SAFE_EVENT_ID.fullmatch(value):
        return value
    return None


@dataclass(frozen=True)
class PrivacyNotice:
    mode: PrivacyMode
    tool_trace_visible: bool
    sensitive_content_allowed: bool

    @property
    def message(self) -> str:
        if self.mode == PrivacyMode.SOFT:
            return (
                "当前为软隐私模式：内容不会进入普通记忆或自动召回，"
                "但宿主前端可能显示工具名称、参数和返回结果。"
                "请勿存入必须对前端使用者保密的内容。"
            )
        return (
            "当前为 gateway 前端隔离模式：私人工具事件不会下发到浏览器。"
            "未分类的工具事件也会被默认阻断。"
            "这不等于 VPS 管理员或模型供应商不可访问运行时明文。"
        )


class GatewayBoundary:
    """Filter private and unclassified tool events before browser transport."""

    def __init__(
        self,
        mode: PrivacyMode | str,
        *,
        public_tool_names: Iterable[str] = (),
    ):
        self.mode = PrivacyMode(mode)
        public_names: set[str] = set()
        for name in public_tool_names:
            public_names.update(_name_candidates(name))
        if public_names & PRIVATE_TOOL_NAMES:
            raise ValueError("a private tool cannot be registered as public")
        self.public_tool_names = frozenset(public_names)

    def classify_event(self, event: dict[str, Any]) -> EventSensitivity:
        names = _tool_name_candidates(event)
        if names & PRIVATE_TOOL_NAMES:
            return EventSensitivity.PRIVATE

        explicit = _explicit_sensitivity(event)
        if explicit is EventSensitivity.PRIVATE:
            return EventSensitivity.PRIVATE
        if names & self.public_tool_names:
            return EventSensitivity.PUBLIC
        if _looks_like_tool_event(event, names):
            return EventSensitivity.UNKNOWN_TOOL
        return EventSensitivity.PUBLIC

    def forward_event(self, event: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(event, dict):
            raise TypeError("event must be a dictionary")
        sensitivity = self.classify_event(event)
        if self.mode == PrivacyMode.GATEWAY and sensitivity is not EventSensitivity.PUBLIC:
            return None
        return event

    def safe_log_record(self, event: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(event, dict):
            raise TypeError("event must be a dictionary")
        sensitivity = self.classify_event(event)
        if sensitivity is EventSensitivity.PUBLIC:
            return event
        return {
            "event_id": _safe_event_id(event.get("event_id")),
            "category": "private_or_unclassified_tool",
            "status": _safe_status(event.get("status")),
            "private": True,
            "arguments_redacted": True,
            "result_redacted": True,
        }


def validate_transport_settings(
    mode: PrivacyMode | str,
    *,
    expose_private_tools_to_client: bool,
    stream_private_tool_events: bool,
    log_private_arguments: bool = False,
    log_private_results: bool = False,
) -> PrivacyMode:
    """Reject contradictory privacy configuration at process startup."""
    parsed_mode = PrivacyMode(mode)
    if log_private_arguments or log_private_results:
        raise ValueError("private arguments and results must never be logged")
    if parsed_mode == PrivacyMode.GATEWAY and (
        expose_private_tools_to_client or stream_private_tool_events
    ):
        raise ValueError(
            "gateway_isolated requires private tools and events to remain server-side"
        )
    return parsed_mode


def notice_for(mode: PrivacyMode | str) -> PrivacyNotice:
    parsed_mode = PrivacyMode(mode)
    if parsed_mode == PrivacyMode.SOFT:
        return PrivacyNotice(
            parsed_mode,
            tool_trace_visible=True,
            sensitive_content_allowed=False,
        )
    return PrivacyNotice(
        parsed_mode,
        tool_trace_visible=False,
        sensitive_content_allowed=False,
    )
