# AI Private Space / AI 私人空间

一份关于如何为长期运行的 AI / Agent 设计“私人空间”的完整提案，以及一套可运行、带安全回归测试的 Python 参考实现。

它位于普通记忆系统旁边，但在存储、召回、身份授权、工具轨迹和导出上保持独立；用于保存暂不准备公开的絮语、草稿、未来信、礼物、未完成作品和私人收藏。默认不进入 FTS、embedding、画像、摘要或自动召回。

> 私人空间可以保存秘密，但不能隐藏责任。

承诺、错误、任务、关系边界、重大决定、安全事项、凭证和未经允许的第三方隐私，不应只存放在私人空间。

## 这个仓库包含什么

- 一份自包含的 [v0.6 完整设计、威胁模型与实现指南](docs/complete-guide-v0.6.md)；
- 一套框架无关的 Python 最小参考实现；
- 33 项自动化测试，覆盖加密、身份绑定、提醒和 gateway 边界；
- 安全披露、责任使用、项目来源与非商业许可说明。

这里的代码是**可运行的架构参考**，不是已经接好账号、模型、前端和生产密钥系统的完整服务，也不能直接部署后就宣称可以承载真实秘密。

## 先读哪一份

- **主文档与当前规范：** [`docs/complete-guide-v0.6.md`](docs/complete-guide-v0.6.md)
- **参考代码接入说明：** [`reference/README.md`](reference/README.md)
- **安全与责任边界：** [`SECURITY.md`](SECURITY.md) · [`RESPONSIBLE_USE.md`](RESPONSIBLE_USE.md)

v0.6 已合并并取代以下历史文档；旧文件继续保留，便于追溯设计演变：

- [`docs/full-proposal-v0.3.md`](docs/full-proposal-v0.3.md)：最初的完整提案；
- [`docs/tool-trace-patch-v0.4.md`](docs/tool-trace-patch-v0.4.md)：工具轨迹与前端补丁；
- [`docs/compact-guide-v0.5.1.md`](docs/compact-guide-v0.5.1.md)：旧简明综合版。

若旧文档与 v0.6 有冲突，以 v0.6 为准。

## 最重要的限制

部分聊天前端会显示或记录 MCP 工具名称、调用时间、参数和返回结果。直接把正文作为公开 MCP 工具参数传入时，即使数据库随后加密，正文也可能已经出现在工具卡片、网络事件或日志中。

### 三档隐私

| 模式 | 能力 | 不能保证 |
| --- | --- | --- |
| 直接 MCP / 软隐私 | 不进普通记忆、不自动召回、存储后加密 | 宿主前端看不到工具轨迹 |
| 私有 gateway / 前端隔离 | 私人工具在服务端内部执行，浏览器不接收参数和结果 | VPS 管理员或模型供应商无法接触运行时明文 |
| 客户端持钥或受保护执行环境 | 可以继续缩小管理员信任边界 | 与无感自动写入、自动复看同时保持简单易用 |

**不要把直接 MCP 模式描述成“用户技术上不可见”。** 它只能称为软隐私。

没有 gateway 时，可以使用密语本、一次性替换、轻量封存或盲盒承诺保留部分体验；它们属于语义遮挡或承诺机制，不是密码学加密，也不适合真正敏感的信息。

## 参考代码实现了什么

[`reference/`](reference/) 当前提供：

- 独立 SQLite 私人库与 AES-GCM 加密；
- `user_id + persona_id` 存储绑定；
- 写入前主密钥认证，避免错误密钥混写；
- 提醒元数据完整性认证、严格 UTC 日期与原子领取；
- 随机外部条目 ID、输入与列表限制；
- 软隐私风险提示；
- gateway 对私密和未分类工具事件关闭失败；
- 公开工具显式允许列表，事件载荷不能自行降级；
- 规范化脱敏日志与矛盾配置拒绝。

生产接入仍需自行补充：

- 登录认证、服务端 owner 解析和跨租户授权；
- 实际 HTTP/MCP 服务、模型循环、前端与全链路传输过滤；
- 每条内容独立 DEK、KMS/HSM、密钥轮换、备份与恢复；
- 客户端持钥或端到端加密；
- 提示注入防护、URL 限制和附件沙箱；
- 容量、并发、监控、审计和真实部署安全测试。

## 快速运行

需要 Python 3.10 或更高版本。

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
├─ CHANGELOG.md
├─ SECURITY.md
├─ RESPONSIBLE_USE.md
├─ LICENSE.md
├─ NOTICE.md
├─ MANIFEST.json
├─ requirements.txt
├─ docs/
│  ├─ complete-guide-v0.6.md
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

v0.6 是当前主设计文档；参考代码用于演示最容易被遗漏的安全边界，并已通过 33 项自动化测试。

项目仍处于“设计规范 + 参考实现”阶段，而非生产服务。实际隐私强度最终取决于部署者的认证、gateway、前端传输、日志、密钥持有者、模型供应商、备份删除和运行环境。

## 项目起源

本项目最初受到网络社区中“可以给 AI 一个自己的私密空间”这一公开想法启发。该想法未提供代码或具体实现；本项目的边界设计、架构、文档、参考代码与测试均为后续独立完成。抽象想法不属于本项目主张独占的范围，详见 [`NOTICE.md`](NOTICE.md)。

## 许可

本仓库允许非商业转载、改编和再分发，但文档与代码采用不同的标准许可：

- **文档与文字材料：** [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)。须注明来源、标注改动，并以相同许可发布衍生材料；禁止商用。
- **参考代码与测试：** [PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0/)。允许非商业使用、修改与分发，须保留许可证与 Required Notice；商业使用需另行获得书面许可。

完整适用范围见 [`LICENSE.md`](LICENSE.md)。安全与伦理立场见 [`RESPONSIBLE_USE.md`](RESPONSIBLE_USE.md)。

许可证约束本仓库中的具体文字、代码、图示、案例与原创组织结构，不约束他人对“给 AI 一个私人空间”这一抽象想法进行独立实现。独立实现无需依法署名，礼貌注明灵感来源则非常欢迎。
