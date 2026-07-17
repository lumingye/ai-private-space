# AI Private Space / AI 私人空间

一个与普通记忆相邻、但在数据、召回和工具边界上独立的 AI 私人空间方案。

它可以保存 AI 暂时不准备公开的絮语、草稿、未来信、礼物、未完成作品和私人收藏；默认不进入普通记忆、不参与 FTS、embedding、画像、摘要或自动召回。

> 私人空间可以保存秘密，但不能隐藏责任。

承诺、错误、任务、关系边界、重大决定、凭证和第三方隐私，不应只存放在私人空间。

## 先读哪一份

- **第一次了解或准备分享：** [`docs/compact-guide-v0.5.1.md`](docs/compact-guide-v0.5.1.md)
- **查看完整设计：** [`docs/full-proposal-v0.3.md`](docs/full-proposal-v0.3.md)
- **查看工具轨迹与前端补丁：** [`docs/tool-trace-patch-v0.4.md`](docs/tool-trace-patch-v0.4.md)

简明版是独立完整文档，不依赖另外两份才能阅读。

## 最重要的限制

部分聊天前端会显示或记录 MCP 工具名称、调用时间、参数和返回结果。

因此，直接把正文作为公开 MCP 工具参数传入时，即使数据库随后加密，正文也可能已经出现在工具卡片、网络事件或日志中。

### 隐私等级

| 模式 | 能力 | 不能保证 |
|---|---|---|
| 直接 MCP / 软隐私 | 不进普通记忆、不自动召回、存储后加密 | 宿主前端看不到工具轨迹 |
| 私有 gateway / 前端隔离 | 私人工具在服务端内部执行，浏览器不接收参数和结果 | VPS 管理员或模型供应商无法接触运行时明文 |
| 客户端持钥或可信执行环境 | 可以继续缩小管理员信任边界 | 与自动写入、自动复看同时保持简单易用 |

**不要把直接 MCP 模式描述成“用户技术上不可见”。** 它只能称为软隐私。

## 无 gateway 时的兼容方案

- 密语本 / 固定代号：语义遮挡，不是加密；
- 一次性替换表：映射表仍需要安全保存；
- 轻量封存：公开调用只传主题和情绪，私有 worker 生成正文；
- 盲盒承诺：只保存“以后要说一件事”和回执，不保存原文。

这些方案适合絮语、惊喜和仪式感，不适合真正敏感信息。

## 参考代码

[`reference/`](reference/) 提供一个框架无关的最小参考实现：

- 独立 SQLite 私人库；
- AES-GCM 加密正文；
- `user_id + persona_id` 身份绑定；
- 只列信封元数据，不自动解密；
- 软隐私警告；
- gateway 事件过滤示例；
- 日志脱敏原则。

它是**架构参考，不是可直接承担真实秘密的生产服务**。部署前仍需补充认证、密钥管理、备份、恢复、并发、审计和安全测试。

## 快速运行参考代码

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m reference.demo
pytest -q
```

演示数据写入临时目录，不包含真实域名、密钥、用户信息或私人内容。

## 仓库结构

```text
ai-private-space/
├─ README.md
├─ SECURITY.md
├─ CHANGELOG.md
├─ requirements.txt
├─ docs/
│  ├─ compact-guide-v0.5.1.md
│  ├─ full-proposal-v0.3.md
│  └─ tool-trace-patch-v0.4.md
├─ reference/
│  ├─ README.md
│  ├─ config.example.yaml
│  ├─ vault.py
│  ├─ boundary.py
│  └─ demo.py
└─ tests/
   ├─ test_vault.py
   └─ test_boundary.py
```

## 项目状态

当前为设计提案与参考实现阶段。核心方向已经明确，但以下部分仍属于实施方责任：

- 前端是否展示工具轨迹；
- gateway 是否真的过滤浏览器事件；
- 服务日志是否包含正文；
- 密钥由谁持有；
- 管理员和模型供应商的信任边界；
- 删除、恢复和跨设备迁移是否经过验证。

## 许可

仓库暂未指定开源许可证。正式公开前，请由维护者决定文档与代码的授权方式；在许可证加入前，不应默认视为可自由复制、修改或再分发。
