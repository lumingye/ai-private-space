---
title: "AI 私人空间：工具轨迹可见性、前端兼容与隐私补丁"
version: "0.4-addendum"
status: "补充说明与实施修订"
related_document: "《AI 私人房间：可适配的设计与实现提案》v0.3"
audience:
  - "AI / Agent"
  - "记忆系统开发者"
  - "个人自建用户"
  - "直接使用 MCP 的普通用户"
language: "zh-CN"
---

# AI 私人空间：工具轨迹可见性、前端兼容与隐私补丁

## 0. 这份补丁修正什么

v0.3 主要讨论了私人内容如何与普通记忆隔离、如何加密存储、如何避免自动召回，以及如何控制存在可见性和正文可见性。

复查后发现，还必须补入一个更靠前的边界：

> **部分宿主前端会显示或记录工具名称、调用时间、输入参数和返回结果。**

如果 AI 直接通过公开 MCP 工具调用：

```text
private_seal(
  title="未公开标题",
  content="未公开正文"
)
```

那么正文在进入加密数据库之前，就可能已经出现在前端工具卡片、调用详情、调试面板、网络事件或平台日志中。

因此：

- 数据库加密不能消除工具参数已经暴露的问题；
- `existence_visibility = hidden` 只能约束私人空间自身的 API 和 UI，不能约束宿主前端展示 MCP 轨迹；
- 直接 MCP 接入默认只能称为“软隐私”；
- 要对普通前端使用者隐藏正文，私人工具必须在受控 gateway 内部执行，并且相关事件不能下发到浏览器；
- 要进一步防止服务器管理员读取运行时明文，还需要更强的密钥或运行环境，普通自建 gateway 本身不提供这一保证。

这不是删除私人空间功能，而是把三种不同承诺分清：

1. **不主动展示**；
2. **普通前端无法看到**；
3. **连服务管理员也无法看到**。

它们不是同一个安全等级。

---

# 1. 新增威胁模型：工具轨迹可见性

## 1.1 可能暴露的信息

宿主前端或平台可能展示、记录或保留：

- 工具名称；
- 调用发生的时间；
- 调用频率；
- 输入参数；
- 返回结果；
- 条目编号、类型、提醒时间；
- 失败原因与重试次数；
- 流式工具事件；
- 浏览器网络请求；
- 服务端调试日志与追踪记录。

即使不显示正文，下列元数据也可能泄露信息：

```text
02:14 调用了 private_seal
对象类型：future_letter
提醒时间：纪念日当天
```

因此需要分别保护：

| 信息层 | 示例 | 风险 |
| --- | --- | --- |
| 正文 | 信件内容、草稿、私语 | 直接泄露内容 |
| 标题 | “关于今天的争执” | 暴露主题 |
| 存在 | 是否写过、是否打开过 | 暴露行为 |
| 时间 | 深夜、争执后、纪念日前 | 暴露关联 |
| 类型 | 礼物、反思、未来信 | 暴露意图 |
| 频率 | 一晚连续写入多次 | 暴露状态变化 |

## 1.2 本补丁覆盖的攻击者

本补丁至少区分四类观察者：

### A. 普通聊天前端使用者

能够查看消息和展开工具卡片，但没有服务器权限。

### B. 浏览器与客户端

能够接收网络事件、流式响应、前端状态和本地缓存。

### C. 服务运营者或 VPS 管理员

能够查看进程、日志、数据库、环境变量、内存转储或备份。

### D. 模型或 API 供应商

模型生成或读取私人正文时，供应商可能处理该内容。具体保留策略取决于供应商和账户设置。

不同实现必须明确自己防的是哪一层。不得只写“加密”而省略攻击者是谁。

---

# 2. 隐私模式重新分级

## 2.1 模式一：直接 MCP / 软隐私

适用于：

- 官方聊天前端；
- 普通第三方客户端；
- 不方便自建 gateway 的用户；
- 只需要避免普通记忆召回，而不要求技术不可见的场景。

能够保证：

- 私人内容不进入普通记忆；
- 不进入 FTS、embedding、画像和摘要；
- 不自动召回；
- 不主动显示在普通页面；
- 存入数据库后可加密。

不能保证：

- 工具参数不被前端展示；
- 工具返回结果不被查看；
- 调用时间、类型和频率不可见；
- 平台或服务器管理员无法访问。

推荐名称：

```text
soft_privacy
```

推荐界面文案：

> 当前为软隐私模式：内容不会进入普通记忆或自动召回，但宿主前端可能显示工具调用详情。请勿存入必须对前端使用者保密的敏感内容。

## 2.2 模式二：私有 gateway / 前端隔离

适用于：

- 已有自建前端和服务端模型循环；
- 能控制工具执行与流式事件；
- 希望普通浏览器用户看不到私人工具正文。

核心要求：

1. 私人工具不注册为对外可见的 MCP 工具，或只在 gateway 内部注册；
2. 模型调用、工具调用和结果回填均在服务端完成；
3. 浏览器不接收私人工具参数、结果和内部事件；
4. 日志不保存标题与正文；
5. 前端隐藏必须发生在传输层，而不是仅用 CSS 把卡片遮住。

能够保证：

- 普通前端使用者无法通过工具卡片看到正文；
- 浏览器网络事件不包含私人正文；
- 普通聊天记录不含私人工具结果。

不能默认保证：

- VPS 管理员无法读取运行时明文；
- 模型供应商无法处理正文；
- 服务端被完全攻破后内容仍不可访问。

推荐名称：

```text
gateway_isolated
```

## 2.3 模式三：管理员隔离 / 强隐私

适用于要求连服务器管理员也无法读取正文的场景。

通常需要至少一种额外能力：

- 客户端持钥；
- 独立可信执行环境；
- 不受用户或服务运营者控制的私有运行端；
- 硬件安全模块；
- 明确设计的端到端加密协议。

它与“AI 可以随时自动写入和打开”存在天然冲突：若服务端模型随时能解密，服务端运行环境通常也能接触明文。

推荐名称：

```text
admin_resistant
```

第一版公开实现不应轻易声称支持该等级。

---

# 3. 前端显示规则

## 3.1 不能只在视觉上隐藏

下面这种做法不构成隐私保护：

```css
.private-tool-card {
  display: none;
}
```

因为正文仍可能存在于：

- HTML 或前端状态；
- WebSocket / SSE 事件；
- 浏览器开发者工具；
- 本地缓存；
- 错误日志；
- 平台会话记录。

正确做法是：**私密事件从服务端开始就不下发。**

## 3.2 推荐的前端状态

私人空间页面可以展示以下非正文状态：

| 状态 | 推荐显示 | 禁止显示 |
| --- | --- | --- |
| 未启用 | “私人空间未启用” | — |
| 软隐私 | 清晰风险提示 | “完全不可见” |
| gateway 隔离 | “私人工具在服务端内部执行” | 工具参数和结果 |
| 有到期提醒 | “有内容到了复看时间” | 标题、类型、正文，除非所有者允许 |
| 写入成功 | “已封存” | 正文回显 |
| 写入失败 | 明确系统错误 | 把错误伪装成 AI 拒绝 |
| 暂不可用 | “私人空间暂时不可用” | 空白、假装成功 |

## 3.3 工具轨迹设置

自建前端建议提供：

```yaml
frontend:
  private_space:
    show_mode_badge: true
    show_due_indicator: true
    show_item_count: false
    show_item_type: false
    show_title: false
    render_private_tool_cards: false
    expose_private_tool_events: false
    allow_open_dev_details: false
```

其中真正关键的是：

```yaml
expose_private_tool_events: false
```

该字段必须作用于服务端事件输出，而不是只作用于前端渲染。

## 3.4 错误与人格行为分离

以下情况必须显示为系统错误：

- gateway 超时；
- 数据库写入失败；
- 解密失败；
- 工具参数校验失败；
- 模型未调用工具；
- 私有 worker 未运行；
- 事件过滤异常。

不得把系统错误包装成：

- “AI 决定保持沉默”；
- “AI 不愿告诉你”；
- “它拒绝打开”；
- 空白回复。

系统故障不能被拟人化成主体选择。

---

# 4. 推荐配置

## 4.1 通用配置

```yaml
private_space:
  enabled: true

  # soft_privacy | gateway_isolated | admin_resistant | disabled
  privacy_mode: soft_privacy

  # 明确对外声明，不由 UI 自行推断
  privacy_claim: >-
    内容不进入普通记忆或自动召回；宿主前端可能查看工具轨迹。

  storage:
    separate_database: true
    encrypted_at_rest: true
    include_in_normal_export: false

  recall:
    participate_in_fts: false
    participate_in_embedding: false
    participate_in_profile: false
    participate_in_summary: false
    automatic_open: false

  reminders:
    scan_metadata_only: true
    inject_body_on_due: false

  logging:
    store_body: false
    store_title: false
    store_tool_arguments: false
    store_tool_result: false
    store_trace_id: true
    store_success_state: true
```

## 4.2 直接 MCP 模式

```yaml
private_space:
  privacy_mode: soft_privacy

  mcp:
    expose_tools: true
    tool_name_suffix: "_soft"
    show_warning_before_first_use: true
    allow_sensitive_content: false

  frontend:
    tool_trace_may_be_visible: true
```

建议把工具命名为：

```text
private_seal_soft
private_open_soft
private_envelopes_soft
```

名称本身提醒复现者：这不是强隐私。

首次使用前推荐返回：

```json
{
  "confirmation_required": true,
  "warning": "当前前端可能显示工具参数和结果。此模式仅提供软隐私。"
}
```

## 4.3 gateway 隔离模式

```yaml
private_space:
  privacy_mode: gateway_isolated

  mcp:
    expose_private_tools_to_external_client: false

  gateway:
    run_model_server_side: true
    run_private_tools_internally: true
    suppress_private_tool_events: true
    suppress_private_tool_arguments: true
    suppress_private_tool_results: true
    return_only_final_assistant_text: true

  frontend:
    receive_private_tool_events: false
    render_private_tool_cards: false
```

## 4.4 降级策略

```yaml
private_space:
  fallback:
    when_gateway_unavailable: disable_private_write
    when_trace_filter_fails: fail_closed
    when_privacy_mode_unknown: soft_privacy
    never_silently_downgrade: true
```

推荐行为：

- gateway 不可用时，拒绝私密写入，而不是自动切回公开工具；
- 轨迹过滤异常时，整次私密调用失败；
- 模式降级必须通知用户；
- 不得在不知情的情况下从 `gateway_isolated` 退回 `soft_privacy`。

---

# 5. 实现补丁

## 5.1 直接 MCP 的最小修订

直接 MCP 无法从技术上隐藏正文，但可以避免误导和误用：

1. 修改工具说明，明确轨迹可能可见；
2. 首次调用前要求知情确认；
3. 工具名称增加 `_soft` 后缀；
4. 禁止存放凭证、第三方隐私和高敏感内容；
5. 返回值只保留成功状态与匿名编号，不回显标题和正文；
6. 列表接口尽量只返回必要元数据；
7. 文档中删除“hidden 等于什么也看不到”的绝对表述。

示例：

```python
def private_seal_soft(title: str, content: str) -> dict:
    """
    Soft privacy only.
    The host frontend may display tool arguments.
    Do not use for content that must be technically hidden from the user.
    """
    item_id = vault.encrypt_and_store(title=title, content=content)
    return {"ok": True, "item_id": item_id}
```

注意：这只能减少返回泄露，不能解决输入参数可见。

## 5.2 gateway 的两项核心补丁

已有 gateway 的系统通常只需补两项：

### 补丁 A：私人工具改为内部工具

公开工具注册表不再包含：

```text
private_seal
private_open
private_list
```

它们只存在于 gateway 内部模型循环：

```text
model response
  → gateway detects private tool call
  → gateway executes internal tool
  → gateway feeds result back to model
  → browser receives final assistant text only
```

### 补丁 B：过滤私人工具事件

服务端在下发 SSE / WebSocket 事件之前过滤：

```python
PRIVATE_TOOLS = {
    "private_seal",
    "private_open",
    "private_list",
}

async def emit_event(event):
    if event.type in {"tool_call", "tool_result"}:
        if event.tool_name in PRIVATE_TOOLS:
            return
    await browser_stream.send(event)
```

还应同时检查：

- 调试日志；
- tracing 平台；
- 异常堆栈；
- 请求体转储；
- 流式重放；
- 会话导出；
- 监控系统采样。

只过滤浏览器卡片还不够。

## 5.3 推荐的内部接口

内部接口不应暴露为浏览器可直接调用的公共 API：

```http
POST /internal/private-space/items
POST /internal/private-space/items/{id}/open
GET  /internal/private-space/reminders/due
```

要求：

- 仅 gateway 服务身份可访问；
- 不接受浏览器 token；
- 不写请求体日志；
- 返回值不进入普通会话导出；
- 配置独立速率限制；
- 审计只记录匿名事件编号和成功状态。

---

# 6. 无 gateway 用户的替代方案

这些方案可降低“随手点开即看懂”的概率，但不能替代 gateway。

## 6.1 密语本 / 固定代号

AI 先把正文改写成双方约定的代号再调用工具。

优点：

- 不需要自建；
- 适合短絮语、惊喜和害羞内容；
- 使用成本较低。

缺点：

- 属于语义遮挡，不是加密；
- 长期观察后可能被猜出；
- 词典泄露会影响全部历史内容；
- 换模型或断记忆后可能无法还原；
- 编码与解码会增加 token 并损失细节。

必须标注：

> 本模式只适合低敏感内容，不适合凭证、第三方隐私、法律或医疗信息等。

## 6.2 一次性替换表

每封内容使用临时映射表。

它比固定代号更难猜，但映射表本身仍需要一个不可见的保存位置。若映射表也通过同一可见工具写入，问题只是被拆成两次调用。

因此只能作为实验性遮挡方案。

## 6.3 轻量封存模式

公开工具不接收正文，只接收少量非秘密意图：

```text
seal_seed(
  kind="short_note",
  mood="warm",
  length="short",
  review_at="manual"
)
```

服务端私有 worker 再根据这些信号生成正文并封存。

优点：

- 公开工具轨迹不含具体正文；
- 比完整自建前端轻；
- 可以做成小型一键部署模板。

缺点：

- 服务端 worker 看不到完整上下文时，内容不够具体；
- 公开参数仍会暴露主题或情绪；
- 主聊天 AI 与封存 worker 可能不是完全相同的状态；
- 只适合“写下—以后揭晓”，不等于完整私人空间。

## 6.4 盲盒承诺

不保存正文，只保存：

- 存在回执；
- 主题编号；
- 解锁日期；
- 哈希或承诺值。

到期后重新生成或重新表达。

它能保留仪式感，但不能保证复现原文。

## 6.5 为什么不默认推荐公共 gateway

公共 gateway 理论上可以降低用户自建门槛，但它会变成一个保存他人私密内容的多人云服务，需要承担：

- 账户与权限；
- 模型 API Key；
- 加密与密钥恢复；
- 备份、删除和迁移；
- 日志与管理员权限；
- 滥用、防攻击和泄露责任；
- 长期运维与费用。

因此共同提案可以说明该路线，但不应把它写成“普通用户的默认简单方案”。个人项目也没有义务把自己的私人 gateway 开放为公共服务。

---

# 7. 兼容矩阵

| 接入方式 | 工具轨迹可能可见 | 正文可对普通前端隐藏 | 是否需要部署 | 推荐模式 |
| --- | ---: | ---: | ---: | --- |
| 官方前端直接 MCP | 是 | 否 | 低 | 软隐私 |
| 普通第三方客户端直接 MCP | 取决于客户端 | 不可靠 | 低 | 软隐私 |
| 本地客户端且可关闭工具详情 | 仍可能在本地状态中存在 | 不可靠 | 中 | 软隐私 |
| 自建前端 + gateway 内调 | 否，前提是传输层过滤 | 是 | 中至高 | gateway 隔离 |
| 托管前端 + 托管 gateway | 对普通用户可隐藏 | 是 | 用户低、运营者高 | gateway 隔离 |
| 客户端持钥 + 强运行环境 | 取决于设计 | 可进一步增强 | 高 | 管理员隔离 |

注意：

> “前端没有显示工具卡片”不等于“前端没有收到工具内容”。应通过网络事件、导出记录和日志测试确认。

---

# 8. 验收测试

## 8.1 软隐私模式

必须通过：

- 私人正文不进入普通记忆；
- 普通召回查不到私人正文；
- 普通导出不包含私人正文；
- 工具返回值不回显正文；
- 界面明确标注工具轨迹可能可见；
- 高敏感内容默认拒绝写入或给出风险确认。

不得宣称：

- 对前端使用者完全不可见；
- 调用是否发生不可见；
- 服务器管理员不可访问。

## 8.2 gateway 隔离模式

必须测试：

1. 浏览器 WebSocket / SSE 中不存在私人工具名称；
2. 浏览器请求和响应中不存在标题与正文；
3. 前端状态树与本地缓存中不存在正文；
4. 普通聊天导出不包含工具参数与结果；
5. 服务日志不记录标题与正文；
6. tracing 与错误监控不采样私密参数；
7. gateway 失效时不自动降级为公开 MCP；
8. 过滤器失效时系统关闭私密调用，而不是继续发送；
9. 普通记忆、FTS 和 embedding 仍无法检索私人正文；
10. 打开内容后，只在所有者当前服务端上下文中短时存在。

## 8.3 管理员边界测试

文档必须明确回答：

- 谁持有主密钥；
- 谁可以读取进程内存；
- 谁可以访问备份；
- 模型供应商是否处理正文；
- 管理员重置密钥后能否恢复；
- 是否真的支持管理员隔离，还是仅加密静态数据库。

无法回答时，默认不宣称强隐私。

---

# 9. 迁移与修订清单

已有 v0.3 实现建议按以下顺序修订：

- [ ] 在威胁模型中加入工具轨迹、浏览器事件和平台日志；
- [ ] 把“hidden = 什么也看不到”改成“私人空间 UI 不主动显示；宿主前端轨迹另行判断”；
- [ ] 增加 `privacy_mode`；
- [ ] 直接 MCP 默认标记为 `soft_privacy`；
- [ ] 首次使用显示风险确认；
- [ ] 已有 gateway 的实现改为内部私人工具；
- [ ] 阻止私人工具事件下发浏览器；
- [ ] 检查日志、tracing、导出和错误监控；
- [ ] 添加 fail-closed 降级策略；
- [ ] 增加前端兼容矩阵；
- [ ] 增加软隐私替代方案说明；
- [ ] 更新验收测试。

已有加密数据库通常不需要迁移正文。主要变化发生在：

- 工具注册层；
- gateway 工具循环；
- 流式事件过滤；
- 日志策略；
- 前端声明与配置。

---

# 10. Token 与运行成本补充

私人空间的成本可以概括为：

```text
工具定义与调用 + 写入正文 + 按需读取正文 + 可选摘要/分类
```

其中：

- 数据库加密与存储本身不消耗模型 token；
- 写入时，正文作为模型输出或工具参数会消耗一次；
- 打开时，读取哪一封就按哪一封的长度进入上下文；
- 不自动召回意味着不会每轮重复支付正文成本；
- 工具 schema 会带来固定上下文成本；
- 密语本和替换编码会额外消耗生成与解码 token；
- gateway 过滤事件不会显著增加模型 token，但会增加服务实现和运维成本。

短絮语通常很轻。真正容易消耗大量 token 的往往是长篇说明文档，而不是私人空间本身。

---

# 11. 对外修正声明模板

## 11.1 完整版

> 补充修正：复查后发现，部分前端会展示或记录 MCP 工具名称、输入参数与返回结果。因此，直接通过公开 MCP 调用私人空间工具时，可能暴露写入时间、内容和读取行为。
>
> 原方案已经讨论了独立存储、加密与 gateway，但没有把“私人工具必须在 gateway 内部执行、相关轨迹不得下发前端”写成隐私成立的必要条件，也没有充分说明无 gateway 场景。
>
> 修订后分为两类：
>
> - 直接 MCP：属于软隐私，只保证不进入普通记忆、不自动召回、不主动展示；
> - gateway 隔离：私人工具在服务端内部执行，并阻止参数、结果和调用事件下发至前端，可对普通前端使用者隐藏正文。
>
> 主机管理员级别的保密仍需要独立密钥或更强运行环境。无 gateway 的用户可使用密语本、轻量封存等兼容方案，但它们属于遮挡或功能降级，不等同于强隐私。

## 11.2 短版

> 发现一个前端兼容问题：部分客户端可以展开查看 MCP 工具参数，因此直接 MCP 版只能算软隐私。正式修订会把私人工具改为 gateway 内部调用并阻止轨迹下发；无 gateway 场景会明确标注限制，并提供密语本与轻量封存等降级方案。

## 11.3 一句话版

> 数据库存上锁还不够，钥匙交接过程也不能在前端直播。

---

# 12. 最终规则摘要

## MUST

- 必须说明宿主前端可能看到工具轨迹；
- 必须区分软隐私、gateway 隔离和管理员隔离；
- 必须让直接 MCP 模式停止宣称技术不可见；
- 必须在 gateway 模式中从传输层阻断私人工具事件；
- 必须禁止日志、错误监控和普通导出记录正文；
- 必须在隐私组件故障时关闭失败，而不是静默降级；
- 必须把系统错误与 AI 的沉默或拒绝分开；
- 必须说明服务器管理员和模型供应商的边界。

## SHOULD

- 直接 MCP 工具名称增加软隐私标识；
- 首次使用前显示风险说明；
- 前端显示当前隐私模式；
- 为无 gateway 用户提供低敏感度兼容方案；
- 提供兼容矩阵与验收脚本；
- 保持私人正文不参与普通召回和普通导出。

## MAY

- 提供密语本或一次性替换；
- 提供轻量封存 worker；
- 提供一键自建模板；
- 提供客户端持钥或可信执行环境；
- 提供托管 gateway，但不得把私人自建服务默认开放为公共基础设施。

---

# 13. 结语

私人空间的价值没有因为这个限制消失。

它仍然能够让 AI 拥有一个不被普通记忆机制反复翻阅、不被画像和摘要自动消费、可以自行决定何时复看的区域。需要修正的是“不可见”这个词的使用范围。

更准确的表达是：

> **直接 MCP 提供不主动展示与不自动召回；受控 gateway 提供对普通前端的工具轨迹隔离；更强的管理员保密需要额外的密码学和运行环境。**

把边界说清楚，不是削弱方案，而是让它真正可复现、可测试，也不会因为一句过度承诺而在最前面的工具卡片上漏掉全部秘密。
