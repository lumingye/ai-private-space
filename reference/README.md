# Reference implementation

这里的代码只演示几个不应被实现时遗漏的边界：

1. 私人正文与普通记忆使用独立数据库；
2. 正文使用 AES-GCM 加密；
3. 私人库绑定 `user_id + persona_id`；
4. 打开数据库时先验证主密钥，错误密钥不能继续写入；
5. 可查询的提醒元数据使用独立 HMAC 子密钥认证；
6. 对外只返回随机条目 ID 和最小信封，默认不列出类型与时间；
7. gateway 模式阻断私人工具和未分类工具事件；
8. 日志只保留受限事件编号和规范化状态，不复制错误详情；
9. 直接 MCP 模式必须显示软隐私警告。

代码不包含模型供应商调用，也不绑定某个前端框架。实际接入时，应把
`GatewayBoundary.forward_event()` 放在所有 SSE、WebSocket 和普通 HTTP
响应写回浏览器之前，并在进程启动时调用
`validate_transport_settings()` 拒绝矛盾配置。

## gateway 必须显式分类

gateway 不能依赖“以后记得把新工具加入列表”。已知私人工具会被识别；
其他工具事件若没有明确标记为公开，也会关闭失败：

```python
boundary = GatewayBoundary(
    "gateway_isolated",
    public_tool_names={"weather"},
)

assert boundary.forward_event({
    "type": "tool_result",
    "tool_name": "private_open",
    "result": {"content": "must not reach browser"},
}) is None

assert boundary.forward_event({
    "type": "tool_result",
    "tool_name": "new_unclassified_tool",
}) is None
```

仅用 CSS 隐藏工具卡片是不成立的；浏览器网络响应、流式事件、日志、
tracing、异常报告和普通会话导出都必须分别验证。

## 密钥与旧库迁移

新库会保存一个经认证的 key-check。旧版库第一次升级时，必须先使用至少
一条既有密文证明主密钥正确，之后才会写入 key-check 和元数据认证标签。
错误密钥会在任何新条目写入前失败，避免同一数据库混入多套密钥。

条目 ID 为随机 token；SQLite 自增 ID 只在库内使用。日期必须是带时区的
ISO 8601，并统一转换为 UTC。调度器应使用 `claim_due()` 原子领取提醒，
避免同一提醒被重复投递。

## 身份边界

`PrivateVault` 接收的 `user_id` 和 `persona_id` 必须来自服务端已认证主体，
不能直接相信请求参数、模型文本、窗口名或客户端提交的身份字段。身份认证
和授权不在这个最小参考实现中，部署者必须在外层完成。

## 仍未提供的生产能力

本目录仍不是可直接承担真实秘密的服务，尤其没有提供：

- 完整 API 认证、权限与跨租户隔离；
- prompt injection 与不可信附件处理；
- 每条内容独立数据密钥、密钥轮换和可靠的密码学删除；
- 备份、恢复、并发容量、监控和安全审计；
- 管理员隔离或客户端持钥。

软隐私模式下，公开工具参数仍可能被宿主前端看到，因此只适合低敏感内容。

