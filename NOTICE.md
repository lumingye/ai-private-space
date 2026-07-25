# Project Origin, Scope, and Related Work / 项目起源、范围与相近实践

This project does not claim originality over the abstract idea of giving an AI a private room or space. Similar concepts may appear independently across communities and long-term-memory or agent projects. The project’s specific product scope, privacy boundaries, tool-trace analysis, gateway model, documentation, reference implementation, and tests were developed around its own use requirements.

本项目不主张“给 AI 一个私人房间 / 空间”这一抽象概念的原创性。相近构想可能在不同社区及长期记忆 / Agent 项目中独立出现。本项目的具体产品定位、隐私边界、工具轨迹分析、gateway 模型、文档、参考实现与测试，均围绕自身使用需求展开。

## Related work / 相近实践

### Closest conceptual neighbour / 最接近的概念实践

- [Yinglianchun/Ombre-Brain — Darkroom](https://github.com/Yinglianchun/Ombre-Brain/blob/main/darkroom.py): a private reflection feature inside a memory system. It stores an AI’s unfinished internal reflections and exposes only limited door/status information before explicit viewing. / 记忆系统中的 AI 私密反思功能，用于保存未完成的内在反思，并在显式查看前只暴露有限门口状态。

Darkroom and this project occupy an adjacent conceptual space, but differ in intended content, system boundaries, lifecycle, and implementation.

Darkroom 与本项目在“普通记忆旁的私人空间”这一概念层相邻，但预期内容、系统边界、生命周期与实现路径不同。

### Adjacent architectural patterns / 相邻架构模式

- [letta-ai/characterai-memory](https://github.com/letta-ai/characterai-memory): separates a shared user memory block from each character’s own persona and individual memories. / 将共享的用户记忆与各角色独立的 persona 和个人记忆分开，体现角色专属状态与共同可见状态的边界。
- [clawdbrunner/openclaw-graphiti-memory](https://github.com/clawdbrunner/openclaw-graphiti-memory): uses three layers—per-agent private files, shared files, and a shared graph—for multi-agent memory. / 采用每个 Agent 的私有文件、共享文件与共享图谱三层结构，展示多 Agent 场景中的私有 / 共享记忆分层。
- [sqliteai/sqlite-memory](https://github.com/sqliteai/sqlite-memory): supports context-scoped selective synchronization so agents can keep private memory separate from shared memory. / 支持按 context 选择性同步，使 Agent 可以把私有记忆与共享记忆分开。

These projects are not equally close to this repository. Darkroom is closest to the product metaphor of a private space; the others are adjacent examples of identity-scoped state, private/shared layering, and selective disclosure. They are listed for context and comparison. Inclusion does not assert direct derivation, use of their code or documentation, or an exhaustive prior-art search.

这些项目与本项目的接近程度并不相同。Darkroom 更接近“私人空间”的产品隐喻，其余项目主要提供角色隔离、私有 / 共享分层或选择性披露方面的相邻架构。此处列出它们仅用于理解和比较相关设计空间；这不表示本项目直接源自、采用或改写了其代码、文档与具体规则，也不构成完整的先例检索。

## Independent implementations / 独立实现

The abstract idea of giving an AI a private space is not exclusive to this repository. Anyone may independently explore or implement a similar idea without using this repository’s protected text, code, diagrams, examples, or original organization.

本项目不主张独占“给 AI 一个私人空间”这一抽象想法。任何人都可以在不复制或改编本仓库文字、代码、图示、案例与原创组织结构的前提下，独立探索或实现相似概念。

Independent implementations are not legally required by this repository’s licenses to provide attribution. A courtesy acknowledgement or link is welcome but optional.

独立实现不因本仓库许可证而负有署名义务；出于礼貌注明相关讨论或链接本项目，均属欢迎但非强制。

When repository materials are copied, translated, adapted, or redistributed, the attribution and noncommercial terms in [`LICENSE.md`](LICENSE.md) apply.

若复制、翻译、改编或再分发本仓库材料，则须遵守 [`LICENSE.md`](LICENSE.md) 中的署名与非商业条款。
