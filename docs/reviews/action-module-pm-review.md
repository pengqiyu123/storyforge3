# PM 审查报告：动作模块化设计反思

> 审查人：Claude Code PM
> 审查对象：`storyforge3/docs/reviews/action-module-design.md`（872 行）
> 审查日期：2026-06-11
> 📦 **时效性（2026-06-14 审核）：历史归档。** 审查对象（动作模块化方案）已被 agent-mode ONLY 取代。保留作 PM 审查方法参考，不作为当前执行依据。
> 参照基线：[research/project-strategy.md](research/project-strategy.md)、[评估.md](../../评估.md)、[豆包意见.md](../../豆包意见.md)
> 当前代码状态：56 API 端点 / 14 Service Protocol / 15 MCP tools / 486 后端 tests

---

## 一、总体判断

**文档洞察力强，但时机不对、力度过重。**

文档准确识别了一个真实问题：SF3 的"动作"分散在 API 路由和 MCP 工具中，缺乏统一的元信息管理、风险分级和确认机制。但提出的解决方案（18 字段 ActionMeta、5 风险等级、7 文件新模块、5 阶段迁移）是典型的过度工程化——投入 4-6 周建构抽象层，换来的用户可感知价值远低于同等时间投入 dogfood、流式输出或自动导演。

**核心矛盾**：该提案与已确认的战略路线（"先做真实 dogfood、长任务可观察化、自动导演最小闭环"）直接冲突。Action Module 是架构优化，不是用户验证。

---

## 二、逐节审查

### §1-3 问题定义：✅ 准确

文档对现状的分析精确：

| 事实 | 验证结果 |
|------|---------|
| "14 Service Protocol 边界清晰" | ✅ `protocols.py` 确认 14 个 Protocol |
| "API 路由按资源拆分" | ✅ 15 个路由文件，56 个端点 |
| "MCP 工具已有 Agent 入口意识" | ✅ 15 tools 有 `[只读]/[LLM 调用]` 标签和 `next_step` |
| "动作没有统一元信息" | ✅ 确认——删除端点不存在、快照恢复无确认、rework 无安全门 |

**问题诊断准确。** 56 个端点 + 15 个 MCP tool 确实缺乏统一的风险分级和确认机制。

### §4 为什么需要 Action Module：⚠️ 理由成立但优先级可商榷

逐条分析：

#### 4.1 "前端和 Agent 对动作的需求不同"

**正确**，但当前 MCP tools 的 `next_step` + 操作类型标签已部分解决。豆包意见中的 8 个参考项目没有一个实现了统一的 Action 层——它们要么是纯 API（AI-Novel-Writing-Assistant）、要么是纯桌面（novelWriter、manuskript）、要么是纯 CLI（snowflake-fiction）。**这不是竞品区分维度。**

#### 4.2 "高风险动作需要统一治理"

**正确**，但实际范围很小：

| 高风险操作 | 当前状态 | 最小修复 |
|-----------|---------|---------|
| 删除书籍 | ❌ 端点不存在 | 加一个 `DELETE /{book_id}` + 确认中间件 |
| 快照恢复 | ⚠️ 无确认 | 在路由加确认参数 |
| rework 模式 | ⚠️ 无确认 | 在 revise 路由加确认检查 |
| 工作区恢复 | ⚠️ 无确认 | 在 workspace 路由加确认 |

这些不需要完整的 Action Module——一个 50 行的 `require_confirmation()` 装饰器或中间件就够了。

#### 4.3 "长任务需要统一进度模型"

**正确**，但已在 Phase 10A-2（SSE 进度 + LLM 流式）中解决。增加 Action 层不会让进度更可见——SSE 事件已经提供 start/progress/complete/error 全生命周期。

#### 4.4 "文档和测试可以由 Action 元信息驱动"

**这是一个好的远期目标，但不是 P0。** 当前 15 个 MCP tool 的 docstring 手动维护得很好（豆包意见确认："MCP 是多数参考项目不具备的能力"）。自动生成文档的投入产出比在用户数为 0 时极低。

### §5-7 接口设计：⚠️ 过度工程化

`ActionMeta` 有 18 个字段、`ActionRisk` 有 5 个等级、`ActionContext` 有 7 个字段、`ActionResult` 使用 Python 泛型。

对比实际需求：

| 字段 | 真正需要 | 当前可以用更简单方式解决 |
|------|---------|----------------------|
| action_id | ✅ 需要 | 用字符串常量 |
| risk (5 级) | ⚠️ 3 级足够：read/modify/destructive | 5 级区分度对单用户本地工具无意义 |
| read_only | ✅ 需要 | MCP 已有 |
| requires_confirmation | ✅ 需要 | 路由级装饰器 |
| supports_dry_run | ❌ 过早 | 只有 delete 需要 dry-run，不是通用需求 |
| supports_undo | ❌ 过早 | 只有 snapshot restore 算"undo" |
| idempotent | ❌ 过早 | 无场景 |
| agent_callable | ✅ 需要 | MCP 已有 |
| long_running | ✅ 需要 | SSE 已有 |
| trace_id | ❌ 过早 | 单用户本地工具不需要分布式追踪 |
| user_intent | ❌ 过早 | Agent 模式未实现 |
| next_steps | ✅ 需要 | MCP 已有 `_suggest_next_step()` |

**18 个字段中只有 6 个是当前必需的**，其中 4 个 MCP tools 已经有。新增 Action 层的边际信息增益极低。

### §8-9 输入/错误设计：✅ 设计质量高

输入显式建模（Pydantic）、禁止暴露文件路径、高风险动作要求确认文本——这些都是好的设计原则。**建议保留这些原则，但作为编码规范而非独立模块。**

ActionErrorCode 的 10 种错误码设计合理，但当前 `api/errors.py` 已有 `ApiError` + HTTP status 映射。再增加一层错误码映射是增加维护负担而非减少。

### §10-11 返回格式/动作分类：✅ 思考完整

30+ 个动作的 5 级分类（只读/低风险/中风险 LLM/高风险/破坏性）思考很完整。`ActionResult` 的 `next_steps` + `affected_resources` 设计对前端和 Agent 都有用。

**但**：这 30+ 个动作中，多少是当前实际存在的？探索发现：
- 删除书籍：端点**不存在**
- 删除章节：端点**不存在**
- 删除快照：端点**不存在**
- 删除 Truth：端点**不存在**
- 工作区重置：端点**不存在**

**文档在设计 5 个不存在的端点的元信息。** 这是典型的推测性设计。

### §12 删除功能设计：✅ 本节最实用

删除功能的设计（自动备份、dry-run、确认文本、返回已删除资源列表）是全文档最有价值的部分。建议**直接落地为具体指令**，不需要等 Action Module。

### §13-14 前端/Agent 调用方式：⚠️ 引入不必要的间接层

`POST /actions/{action_id}` 通用端点在 REST API 之上又加了一层 RPC 风格调用。这会让 OpenAPI 文档失去资源语义，增加前端理解成本。保持资源式 API（`POST /books/{id}/draft`）更符合 Web 标准。

MCP 工具由 Action Registry 自动生成（§14）是一个好主意，但当前 15 个 tool 手动维护成本极低（豆包确认这是 SF3 的差异化优势），自动化的紧迫性不高。

### §16-17 测试和实施顺序：✅ 渐进思路正确

5 阶段渐进式迁移思路正确，不推翻现有架构。但即使渐进，Phase A（基础设施）也需要新建 5 个文件 + 3 个基础类 + 注册表 + 测试，估算 1-2 周工作量。

### §18 最终判断：⚠️ 结论正确但优先级判断与战略冲突

文档说"如果项目只面向人工前端操作，当前设计短期可用"——**这正是当前状态**。系统 0 真实用户、0 dogfood 记录。先建构抽象层再验证产品假设，是典型的本末倒置。

---

## 三、竞品对标验证

豆包意见中的 8 个参考项目的动作管理模式：

| 项目 | 动作管理方式 | SF3 当前水平 |
|------|------------|------------|
| AI-Novel-Writing-Assistant | 直接 API + Job Queue（7 阶段状态机） | ✅ SF3 的 SSE + ChapterWorkflow 更强 |
| snowflake-fiction | 直接函数调用 + 方法论规则 | ✅ SF3 的 Protocol 层更强 |
| novelWriter | 直接 API + 项目树 | ≈ 相当 |
| manuskript | 直接 API + 卡片视图 | ≈ 相当 |
| 91Writing | 基础 API | ✅ SF3 更强 |
| InkOS | Agent 驱动 + tool 调用 | ✅ SF3 的 MCP 更系统化 |

**结论**：没有任何竞品实现了 Action Module 式的统一动作层。SF3 当前的 Service Protocol + MCP tools + SSE 事件已经是竞品中最好的。Action Module 不是竞争差异化的方向。

---

## 四、风险评估

| 风险 | 概率 | 影响 | 说明 |
|------|------|------|------|
| 延迟战略路线图 | **高** | **高** | Action Module 全量实施需要 4-6 周，直接推迟 dogfood 和自动导演 |
| 过早抽象导致返工 | **高** | **中** | dogfood 后管线设计可能大变（prompt 质量问题、审计误判），Action 接口需要跟着改 |
| 增加维护负担 | **中** | **中** | 56 个端点 + 15 MCP tool + 30+ Action = 三层维护，Codex 的认知负担增大 |
| 对真实用户无感知 | **高** | **高** | 用户不会因为"有了 ActionMeta"就觉得产品更好用 |

---

## 五、决策建议

### 推荐：取其精华，渐进吸收，不建独立模块

文档中真正有价值的部分**不是** Action Module 层本身，而是它背后的设计原则。建议将这些原则分散落地到现有架构中，而非新建独立模块。

### 具体吸收方案

#### 1. 立即可做（Phase 10A 期间，≤2 天）

**删除端点 + 确认机制**：文档 §12 的删除设计是全文档最有价值的部分。

```
不在 actions/ 新建模块，而是在 api/routes/books.py 加：
- DELETE /{book_id}?confirm_text=xxx
- 自动创建 zip 备份
- 返回已删除资源列表
```

同样为 snapshot restore 和 workspace restore 加确认参数。这些改动只需改 3 个路由文件，≤100 行代码。

#### 2. Phase B 期间（自动导演开发时）

**动作元信息作为编码规范而非独立模块**：

在 `CLAUDE.md` 或 `docs/coding-standards.md` 中新增"动作设计规范"：
- 所有新端点必须标注风险等级（通过 docstring 或常量）
- 高风险端点必须有确认参数
- 长任务端点必须发布 SSE 事件
- MCP tool 必须有 `next_step`

这让原则落地但不需要独立模块。

#### 3. Phase C 期间（产品化打磨时）

**评估是否需要 Action Registry**：

Phase B 的自动导演会产生 `AutoDirectorService`，它需要链式调用 10+ 个 Service。此时可以评估：
- 如果链式调用的编排复杂度确实需要统一元信息 → 引入轻量 Action Registry
- 如果 ChapterWorkflow + BookStateMachine 够用 → 继续用现有架构

**让真实需求驱动架构决策，而非架构决策驱动产品。**

### 不推荐的做法

- ❌ 不建 `actions/` 独立目录（至少在 dogfood 之前）
- ❌ 不建 ActionRegistry（当前 15 MCP tool 的手动注册足够）
- ❌ 不建 `POST /actions/{action_id}` 通用端点（保持 REST 资源式 API）
- ❌ 不在 Phase 10A/10B 期间做 Action Module 迁移

---

## 六、总结评分

| 维度 | 评分 | 说明 |
|------|------|------|
| 问题识别 | **A** | 准确找到动作分散、缺乏统一治理的真实痛点 |
| 方案设计质量 | **A-** | 接口设计严谨，分类完整，但过度工程化 |
| 时机判断 | **D** | 与已确认的战略路线冲突，属于过早优化 |
| 优先级判断 | **C** | P0 应是 dogfood 而非架构层，删除功能设计是唯一 P0 |
| 竞品对标 | **C** | 未参考任何竞品的做法，无竞品实现了 Action Module |
| 可执行性 | **B-** | 渐进思路正确，但即使是 Phase A 也需要 1-2 周 |
| 与战略契合度 | **D** | 直接推迟 Phase A（dogfood + 可观察化）和 Phase B（自动导演） |

**一句话总结**：这是一份优秀的架构研究文档，应该归档为 ADR 参考，但不应该变成下一阶段的执行计划。先跑真实 dogfood，再决定架构方向。
