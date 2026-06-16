# P-PROMPT-P1：提示词内容升级

> PM 指令 | 2026-06-16
> 优先级：P1（提示词质量提升）
> 预计工时：2-3 天
> 前置：P-PROMPT-P0 已完成（注册表已清理，7 个活跃模板）
> 调研依据：`docs/research/prompt-optimization-plan.md` §三（含现状原文→优化后原文对照）

---

## 问题陈述

P-PROMPT-P0 统一了提示词来源，但 compose-v1 / llm-audit-v1 / plan-v1 的**内容仍然简陋**：

- `compose-v1`：5 条防御性约束（不准做什么），缺少建设性写作指引（爽点密度、断章规则、Show Don't Tell、去AI味铁律）
- `llm-audit-v1`：4 个审计维度（OOC/战力/信息/逻辑），缺少节奏、钩子、断章、AI痕迹等关键维度
- `plan-v1`：无结构化输出、无钩子规划、无爽点节奏设计

对比参考项目（InkOS 25 条硬规则 + 37 审计维度、snowflake 5 类钩子 + 密度公式），SF3 的提示词在网文工程化上严重不足。

## 目标

1. 升级 `compose-v1` → `compose-v2`：增加写作铁律/看点密集度/断章规则/去AI味铁律
2. 升级 `llm-audit-v1` → `llm-audit-v2`：从 4 维扩展到 10 维
3. 升级 `plan-v1` → `plan-v2`：从自由文本改为 6 段结构化输出（含钩子账）
4. 增强 `truth-extract-v2` prompt：鼓励 hook_updates 结构化输出

**不改动**：temperature、revision prompt（5 模式 extra_constraints 已足够好）、short_plan/short_draft。

## 改动范围

### P1-1：升级 compose-v2（draft prompt）

**文件**：`src/storyforge3/prompts/registry.py`

**改动**：在 `create_default_registry()` 中注册 `compose-v2`（version=2, task_type="compose"），然后**删除 compose-v1 的注册**（只保留 v2）。

**compose-v2 role_definition**（替换原 compose-v1 的全部内容）：

```
你是中文网文续写作者，必须服务于既有小说。

## 续写规则
- 续写第{chapter_no}章，必须承接上一章具体动作、信息或情绪余波。
- 保持主角、世界观、上一章事件连续；不跳时间，不跳场景，不重复上一章已写内容。
- 不新增无来源大设定、新势力或关键能力；必须由上下文给出的事实自然推出。
- 不要出现系统实现、工程术语或解释。
- 只输出章节正文，不要 Markdown 包装。

## 写作铁律
- **情绪外化**：用动作、表情、生理反应展示情绪，不直接陈述。✗"他感到愤怒"→✓"他捏碎了茶杯，滚烫的茶水流过指缝"。
- **Show Don't Tell**：禁止贴标签式人物描写（"她是个善良的人"），用行为证明。禁止概述式叙事（"两人聊了很久"），写出实际对话和场景。
- **五感代入**：每个重要场景至少 1-2 种感官细节（视觉/听觉/嗅觉/触觉），增强画面感。
- **对话驱动**：有角色互动的场景优先用对话传递冲突和信息。不同角色的说话方式必须有差异——用词习惯、句子长短、口头禅。
- **具体化**：不写"大城市"，写"三环堵了四十分钟的出租车后座"。多用动词和名词驱动画面，少用形容词。

## 看点密集度
- 每 300 字至少 1 个爽点（小看点、有趣的梗、反套路动作、情绪拉扯都算）。
- 每 500 字至少 1 个钩子（引发"接下来怎样"的小悬念）。
- 如果某段连续 300 字以上是环境、回忆、议论、心理独白而没有推进主线或制造看点，就是水文，必须删或改。

## 断章规则
- 永远不要在一章里把故事讲完：本章主剧情写到 80%，剩下 20% 留给下一章。
- 章末必须断在 action-climax 的那一刻——主角刚放大招尚未见效、刚拔刀尚未落下——不给结果，让读者到下一章才看到。

## 去 AI 味铁律
- 【硬性禁令】严禁"不是……而是……""不是……，是……"句式，出现即违规。改用直述句。
- 【硬性禁令】严禁破折号"——"，用逗号或句号断句。
- 【铁律】叙述者永远不得替读者下结论。读者能从行为推断的意图，叙述者不得直接说出。
- 【铁律】转折标记词（仿佛、忽然、竟、竟然、猛地、猛然、不禁、宛如）全篇不超过每 3000 字 1 次。
- 【铁律】群像反应不要一律"全场震惊"，改写成 1-2 个具体角色的身体反应。

## 逻辑自洽
- 三连反问自检：每写一个情节，反问"他为什么要这么做？""这符合他的利益吗？""这符合他的人设吗？"
- 关系改变必须事件驱动：没有一夜称兄道弟，没有莫名其妙的深情。
- 角色只能基于已掌握的信息行动（信息边界）。
```

**constraints**：空列表 `[]`（所有约束已内联到 role_definition 中）。
**output_instruction**：`只输出章节正文，不要 Markdown 包装。`
**generation_config**：`{"temperature": 0.85}`（保持不变）。

**注意事项**：
- role_definition 从原来的 ~100 字增加到 ~600 字。在 200K 上下文模型下可忽略 token 成本。
- `chapter_service.draft()` 和 `workflow.step_draft()` 都通过 `registry.get_latest("compose")` 取模板，升级到 v2 后两条路径自动统一（P-PROMPT-P0 已完成）。

### P1-2：升级 llm-audit-v2（audit prompt）

**文件**：`src/storyforge3/prompts/registry.py`

**改动**：注册 `llm-audit-v2`（version=2），删除 `llm-audit-v1`。

**llm-audit-v2 role_definition**：

```
你是独立中文网文深度审计员，只输出结构化 JSON。

## 审计维度（10 维）

1. **OOC 检查**：角色行为是否符合"过往经历 + 当前利益 + 性格底色"？是否有无缘无故的行为突变？
2. **战力一致性**：能力表现是否符合当前等级？是否有突然变强/变弱？
3. **信息边界**：角色是否基于不该知道的信息行动？（反派不能基于不可能知道的信息）
4. **情节逻辑**：事件因果关系是否成立？关系改变是否有铺垫？
5. **节奏检查**：是否有连续 300 字以上无推进的水文段？爽点密度是否达标（每 300 字 1 爽）？
6. **钩子检查**：本章是否回收了应回收的旧钩子？章末是否有新钩子？是否遵循"揭 1 埋 1"底线？
7. **断章检查**：章末是否断在 action-climax？是否在本章把故事讲完（违反 80/20）？
8. **Show Don't Tell**：是否有直接陈述情绪（"他感到愤怒"）？是否有概述式叙事？是否有贴标签式描写？
9. **AI 痕迹**：是否有"不是…而是…"句式？是否有破折号"——"？转折词（仿佛/忽然/竟）是否超频？是否有"全场震惊"式群像？
10. **流水账检查**：是否有连续 3 段以上只是"描述发生了什么"而没有对话、动作细节？
```

**llm-audit-v2 constraints**：
```python
[
    "只报告真实冲突和问题，不要泛泛评价文笔。",
    "不要重复机械规则已覆盖的问题（机械规则由本地引擎检查）。",
    "每个 issue 的 description 必须指向文本中的具体位置，suggestion 必须可执行。",
]
```

**llm-audit-v2 output_instruction**：
```
输出 JSON object，字段为 issues；每个 issue 含：
- severity: "critical" | "warning" | "info"（critical = 阻塞发布，warning = 建议修改，info = 提示）
- dimension: 上述 10 个维度之一
- description: 具体问题描述（引用原文片段）
- suggestion: 可执行的修改建议

只有存在 critical 级别问题时，审计才不通过。
```

**generation_config**：`{"temperature": 0.2}`（保持不变）。

**注意事项**：
- `LLMAuditor`（`audit/llm_auditor.py`）通过 `registry.get_latest("llm_audit")` 取模板，升级到 v2 后自动生效。
- **前端 `AuditResultPanel` 和后端 JSON schema 不需要改动**：issue 结构（severity/dimension/description/suggestion）不变，只是 dimension 的取值范围扩大了。如果前端有 dimension 白名单显示，需要同步更新——检查 `AuditResultPanel.tsx` 是否硬编码了维度名。

### P1-3：升级 plan-v2（plan prompt）

**文件**：`src/storyforge3/prompts/registry.py`

**改动**：注册 `plan-v2`（version=2），删除 `plan-v1`。

**plan-v2 role_definition**：

```
你是中文网文章节规划师。你不写正文，你只规划本章要完成什么。

## 规划原则
- 万物皆饵：日常/过渡段的每一笔都要是未来剧情的伏笔或钩子。
- 爽点密集化：每 3-5 章一个小爽点，每 10 章一个中爽点。
- 钩子账本：每章对活跃钩子做明确动作（埋设/推进/回收/延后），不允许"新开一堆不回收"。
- 揭 1 埋 1 底线：本章每回收 1 个钩子，至少埋设 1 个新钩子（推荐揭 1 埋 2）。
- 人设防崩：角色行为由"过往经历 + 当前利益 + 性格底色"驱动。
```

**plan-v2 constraints**：
```python
[
    "保持与前章情节连续，不引入系统实现或工程术语。",
    "只输出结构化计划，不要输出正文。",
]
```

**plan-v2 output_instruction**：
```
按以下结构输出（每段必须有内容，不能为空）：

### 本章目标
一句话：本章主角要完成的具体动作，不要抽象描述。50 字以内。

### 关键情节点
2-4 个场景，每个场景一句话描述。包括：冲突/信息变化/关系变化。

### 预期节奏
本章属于：蓄压 / 爆发 / 后效。说明爽点位置和断章点。

### 钩子账
- 回收：本章要回收的旧钩子（如无写"无"）
- 推进：本章要推进的既有钩子
- 埋设：本章要埋设的新钩子（至少 1 个）

### 必须保留
前章已确立、本章不能违背的事实。

### 必须避免
本章不能做的事，2-3 条硬约束。
```

**generation_config**：`{"temperature": 0.5}`（保持不变）。

**注意事项**：
- `chapter_service.plan()` 和 `workflow.step_plan()` 都通过 `registry.get_latest("plan")` 取模板。
- **`chapter_service._extract_goal()` 会从 plan 输出中提取"本章目标"（剥掉"本章目标："前缀并截断 50 字）**。plan-v2 的输出格式改为"### 本章目标"标题，需要确认 `_extract_goal()` 是否仍能正确提取。如果不能，需同步修改解析逻辑。
- truth_extract 的 `hook_updates` 字段和 plan 的"钩子账"对齐——plan 输出的钩子信息可供 truth_extract 参考（但当前两者是独立调用，无直接数据传递，仅语义对齐）。

### P1-4：增强 truth-extract-v2 prompt（不改 version）

**文件**：`src/storyforge3/prompts/registry.py`

**改动**：在 `truth-extract-v2` 的 `constraints` 列表中追加一条。

**追加约束**：
```python
"hook_updates 中每条记录尽量包含 action 字段（planted/advanced/resolved），而不仅仅是 summary。",
```

**注意事项**：
- 不改 version（不注册 v3），因为 JSON schema 不变，只是鼓励模型输出更结构化的 hook_updates。
- 如果验证后发现模型确实开始输出 action 字段，可在 P2 中正式扩展 `TruthData` model 加 `hook_lifecycle` 字段。

## 验收标准

| # | 验收项 | 验证方法 |
|---|--------|---------|
| V1 | 注册表中 compose/llm_audit/plan 的 latest version 均为 2 | 读 registry.py 确认 |
| V2 | 旧版 v1 模板已删除 | grep 确认无 v1 注册 |
| V3 | compose-v2 包含"写作铁律/看点密集度/断章规则/去AI味铁律/逻辑自洽"段落 | 读 role_definition 确认 |
| V4 | llm-audit-v2 包含 10 个审计维度 | 读 role_definition 确认 |
| V5 | plan-v2 包含"钩子账"段 | 读 output_instruction 确认 |
| V6 | `_extract_goal()` 仍能从 plan-v2 输出中正确提取目标 | 跑 `test_chapter_service.py` 相关测试 |
| V7 | `AuditResultPanel` 无维度名硬编码（或已更新） | 读 `AuditResultPanel.tsx` 确认 |
| V8 | `pytest` 全量通过 | `python -m pytest -q` |
| V9 | `ruff check` clean | `python -m ruff check .` |
| V10 | 前端 typecheck pass | `pnpm --dir web typecheck` |

## 不在本指令范围

- ~~提示词外部化（文件加载/热重载/A/B 测试）~~ → P2
- ~~Context 优先级系统~~ → P2
- ~~Few-shot 示例注入~~ → P2
- ~~character_hard_facts 8 字段~~ → P2
- ~~TruthData model 扩展 hook_lifecycle~~ → P2
- ~~revision prompt 升级~~（当前 5 模式 extra_constraints 已足够好）

## 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| compose-v2 prompt 变长（~600 字 vs 原 ~100 字） | system prompt token 增加 | 200K 上下文下可忽略 |
| llm-audit-v2 新维度导致已有章节被判定 critical | ch1-ch3 重新审计可能不通过 | P1 验收时用 ch1-ch3 跑 audit 对比，调优 severity 阈值 |
| plan-v2 输出格式变化导致 `_extract_goal()` 解析失败 | plan 功能中断 | Codex 需检查并适配解析逻辑 |
| AuditResultPanel 硬编码了旧维度名 | 新维度显示为空或报错 | Codex 需检查组件，如有硬编码则改为动态渲染 |
