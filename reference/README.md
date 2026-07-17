# Reference implementation

这里的代码只演示几个不应被实现时遗漏的边界：

1. 私人正文与普通记忆使用独立数据库；
2. 正文使用 AES-GCM 加密；
3. 私人库绑定 `user_id + persona_id`；
4. 列表接口只返回信封元数据；
5. 直接 MCP 模式必须显示软隐私警告；
6. gateway 模式应在服务端过滤私人工具事件；
7. 日志只记录成功、失败和匿名事件编号，不记录标题与正文。

代码不包含模型供应商调用，也不绑定某个前端框架。实际接入时，应把 `GatewayBoundary.forward_event()` 放在所有 SSE、WebSocket 和普通 HTTP 响应写回浏览器之前。

## 不要做的事

```python
# 错误：只在页面上隐藏工具卡片，但网络响应仍有正文
browser_event = private_tool_event
css_hide(browser_event)
```

正确原则：

```python
browser_event = boundary.forward_event(private_tool_event)
assert browser_event is None
```

软隐私模式下，公开工具参数仍可能被宿主前端看到，因此只适合非敏感内容。
