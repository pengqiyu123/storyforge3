# StoryForge3 提示词优化方案（基于 SF2 参考项目原文对比）

> PM 优化方案 | 2026-06-16
> 基础：`docs/research/prompt-optimization-research.md`（基线） + 本文档（原文对比 + 优化方案）
> 原则：**小说生产本位**——优化服务于产出质量，不做架构炫技。分级实施，P0 先行。

---

## 一、核心结论

经过对 InkOS / AI-Novel-Writing-Assistant / snowflake-fiction 三个项目的逐字原文对比，SF3 提示词存在 **三大类差距**：

| 差距类别 | 核心问题 | 严重度 |
|---|---|---|
| **A. 结构性缺陷** | 双轨制、孤儿模板、占位符静默失败 | 🔴 P0（不改内容就能修） |
| **B. 内容缺失** | draft 缺爽点/断章/Show Don't Tell；audit 维度太少；plan 无钩子账本 | 🟡 P1（改内容，提质量） |
| **C. 工程化不足** | 无外部化、无 Few-shot、无 context 优先级 | 🟢 P2（基础设施升级） |

**建议路径**：先 P0 消除缺陷（1-2 天）→ P1 增强内容（3-5 天）→ P2 工程化（后续迭代）。每级独立可交付，P0 完成后即可下发 PROD-2 验证。

---

## 二、P0：消除结构性缺陷（不改提示词内容）

### P0-1：统一 draft 双轨制

**现状**：
- `chapter_service.py` 内联 `CHAPTER_DRAFT_PROMPT`（7 条写作约束）
- `workflow.py` 用注册表 `compose-v1`（5 条续写约束）
- 两条路径产出风格不一致

**优化**：
1. 删除 `chapter_service.py` 的 `CHAPTER_DRAFT_PROMPT` 常量
2. `chapter_service.draft()` 改为从注册表取 `compose` 模板
3. P1 阶段再统一升级 `compose-v1` 内容（P0 只统一来源，不改内容）

**风险**：低。两条路径合并到同一模板，风格一致性提升。

### P0-2：统一 length_normalize 双轨制

**现状**：
- 注册表 `length-normalize-v1` 未被使用
- `LengthNormalizer._prompt()` 用内联动态 prompt

**优化**：
1. 删除注册表 `length-normalize-v1`（孤儿）
2. 或：让 `LengthNormalizer` 改用注册表模板（需扩展模板支持 `{verb}` 占位符）

**推荐**：方案 1（删除孤儿），因为内联版已经够用。

### P0-3：清理孤儿模板

- `audit-v1`：注册了但无引用（真正用的是 `AuditRunner` 纯规则 + `llm-audit-v1`）→ **删除**
- `length-normalize-v1`：见 P0-2 → **删除**
- `truth-extract-v1`：被 v2 取代 → **删除**（registry 已有 version 机制，保留旧版无意义）

### P0-4：修复 `_SafeDict` 静默失败

**现状**：`registry.py` 的 `render_system_prompt()` 用 `_SafeDict`，未定义占位符原样保留 `{xxx}` 发给模型。

**优化**：增加严格模式参数 `strict=True`，占位符未定义时抛 `KeyError`。默认非严格（向后兼容），但渲染时记录 warning 日志。

---

## 三、P1：增强提示词内容（核心质量提升）

### P1-1：升级 draft prompt（compose-v2）

**现状原文（compose-v1）**：
```
你是中文网文续写作者，必须服务于既有小说。
续写第{chapter_no}章，必须承接上一章具体动作、信息或情绪余波。
保持主角、世界观、上一章事件连续；不跳时间，不跳场景，不重复上一章已写内容。
不新增无来源大设定、新势力或关键能力；必须由上下文给出的事实自然推出。
不要出现系统实现、工程术语或解释。
只输出章节正文。
```

**借鉴来源**：
- InkOS `WritingCraftCard`（15 条写作铁律精简版）
- InkOS `CoreRules` 看点密集度 + 80/20 断章
- snowflake `Show Don't Tell` 7 条规则
- InkOS 去AI味铁律 + 硬性禁令

**优化后原文（compose-v2，建议）**：
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

**变化**：
- 5 条 → 6 大节（续写规则/写作铁律/看点密集度/断章规则/去AI味/逻辑自洽）
- 新增 15 条建设性约束（来自 InkOS + snowflake）
- 保留原有 5 条防御性约束
- temperature 保持 0.85（创意性）

### P1-2：升级 audit prompt（llm-audit-v2）

**现状原文（llm-audit-v1）**：
```
你是独立中文网文深度审计员，只输出结构化 JSON。
审计维度：OOC、战力一致性、信息边界、情节逻辑。
...
```

**现状问题**：4 个维度太少，缺少节奏、钩子、AI 痕迹等关键维度。

**借鉴来源**：
- InkOS 37 维度（精选适合 SF3 的 10 个）
- snowflake 5 套一致性检查
- AI-Novel 6 维度评分（coherence/repetition/pacing/voice/engagement/logic）

**优化后原文（llm-audit-v2，建议）**：
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

## 审计原则
- 只报告真实冲突和问题，不要泛泛评价文笔。
- 不要重复机械规则已覆盖的问题（机械规则由本地引擎检查）。
- 每个 issue 的 description 必须指向文本中的具体位置，suggestion 必须可执行。

## 输出格式
输出 JSON object，字段为 issues；每个 issue 含：
- severity: "critical" | "warning" | "info"（critical = 阻塞发布，warning = 建议修改，info = 提示）
- dimension: 上述 10 个维度之一
- description: 具体问题描述（引用原文片段）
- suggestion: 可执行的修改建议

只有存在 critical 级别问题时，审计才不通过。
```

**变化**：
- 4 维 → 10 维（新增节奏/钩子/断章/Show Don't Tell/AI痕迹/流水账）
- 新增 severity 三级判定标准
- 新增"审计原则"约束模型不泛泛而谈
- temperature 保持 0.2（确定性）

### P1-3：升级 plan prompt（plan-v2）

**现状原文（plan-v1）**：
```
你是中文网文章节规划师。
基于已有上下文，规划第{chapter_no}章的核心目标、冲突点和场景安排。
只输出章节计划（目标 + 关键情节点 + 预期节奏），不要输出章节正文。
保持与前章情节连续，不引入系统实现或工程术语。
只输出章节计划，不要输出正文。
```

**现状问题**：无结构化输出、无钩子规划、无爽点节奏。

**借鉴来源**：
- InkOS `ChapterMemoContract`（7 段计划模板）
- InkOS `Planner` hook 账本（open/advance/resolve/defer + 揭1埋2）
- snowflake 爽点密度阶梯

**优化后原文（plan-v2，建议）**：
```
你是中文网文章节规划师。你不写正文，你只规划本章要完成什么。

## 规划原则
- 万物皆饵：日常/过渡段的每一笔都要是未来剧情的伏笔或钩子。
- 爽点密集化：每 3-5 章一个小爽点，每 10 章一个中爽点。
- 钩子账本：每章对活跃钩子做明确动作（埋设/推进/回收/延后），不允许"新开一堆不回收"。
- 揭 1 埋 1 底线：本章每回收 1 个钩子，至少埋设 1 个新钩子（推荐揭 1 埋 2）。
- 人设防崩：角色行为由"过往经历 + 当前利益 + 性格底色"驱动。

## 输出格式（结构化文本）

### 本章目标
<一句话：本章主角要完成的具体动作，不要抽象描述。50 字以内>

### 关键情节点
<2-4 个场景，每个场景一句话描述。包括：冲突/信息变化/关系变化>

### 预期节奏
<本章属于：蓄压 / 爆发 / 后效。说明爽点位置和断章点>

### 钩子账
- 回收：<本章要回收的旧钩子，如无写"无">
- 推进：<本章要推进的既有钩子>
- 埋设：<本章要埋设的新钩子，至少 1 个>

### 必须保留
<前章已确立、本章不能违背的事实>

### 必须避免
<本章不能做的事，2-3 条硬约束>

## 规划约束
- 保持与前章情节连续，不引入系统实现或工程术语。
- 只输出上述结构化计划，不要输出正文。
```

**变化**：
- 新增 5 条规划原则（钩子账本/揭1埋1/万物皆饵等）
- 输出从"自由文本"改为 6 段结构化（目标/情节点/节奏/钩子账/必须保留/必须避免）
- 钩子账本对齐 truth_extract 的 hook_updates 字段

### P1-4：增强 truth_extract 的 hook_updates（truth-extract-v3）

**现状**：`hook_updates` 只要求 `summary` 字段。

**优化**：扩展为结构化，对齐 plan 的钩子账本：
```json
"hook_updates": [
  {
    "hook_id": "可选，已有钩子的 ID",
    "action": "planted | advanced | resolved",
    "summary": "钩子内容或变化描述",
    "lifecycle": "planted → pressured → near_payoff → cleared"
  }
]
```

**注意**：这是 schema 层改动，需要同步 `TruthData` model 和前端类型。P1 阶段可先只改 prompt 鼓励结构化输出，schema 强制留到 P2。

---

## 四、P2：工程化升级（后续迭代）

### P2-1：提示词外部化

**现状**：所有 prompt 硬编码 Python，`prompts/system/` 和 `prompts/tasks/` 是空占位。

**优化方向**（参考 AI-Novel PromptAsset）：
1. 每个 prompt 存为 `prompts/tasks/{task_type}.md`（system prompt）+ `prompts/tasks/{task_type}.user.md`（user template）
2. `registry.py` 改为从文件加载，支持热重载
3. 支持版本覆盖：`prompts/tasks/draft.v2.md` 覆盖默认 `draft.v1.md`
4. 支持环境变量 `SF3_PROMPTS_DIR` 指向自定义目录（A/B 测试）

**优先级**：P2。当前 3 章生产不需要，但 10+ 章后提示词迭代频繁时必需。

### P2-2：Context 优先级系统

**现状**：`ContextPackage` 按 6 个 block 固定优先级拼装，12000 字预算。

**优化方向**（参考 AI-Novel `contextRequirements` 104→72）：
1. 每个 context block 标注 `priority`（数字越大越不可丢）
2. token 超限时按 `dropOrder` 裁剪
3. `book_contract=104 > chapter_goal=100 > character_hard_facts=99 > truth=95 > world_rules=90 > previous_tail=85`

**优先级**：P2。当前 3 章的 context 未超预算，10+ 章后 truth 积累可能导致超预算。

### P2-3：Few-shot 示例注入

**现状**：所有 prompt 都是 zero-shot。

**优化方向**：
1. `truth_extract` 的 user payload 注入 1 个正确输出示例
2. `llm_audit` 的 user payload 注入 1 个 critical issue 示例 + 1 个 warning issue 示例
3. `revise` patch 模式注入 1 个 find/replace 示例

**优先级**：P2。能提升 JSON 输出准确率，但当前 schema 校验已能兜底。

### P2-4：character_hard_facts 机制

**借鉴** AI-Novel 的 8 字段铁律：
- `identityLabel / factionLabel / stanceLabel / powerLevel / realm / currentLocation / availability / prohibitions`
- writer 前必须带 `character_hard_facts` required context

**优化方向**：
1. `Character` model 扩展这 8 个字段（当前只有 name/role/profile/personality）
2. draft 的 context package 强制包含 character_hard_facts block
3. audit 增加硬事实违背检测维度

**优先级**：P2。需要数据模型改动，但能大幅减少 OOC。

---

## 五、实施路线图

### 第一批（P0，1-2 天，立即实施）
- [ ] P0-1：统一 draft 双轨制
- [ ] P0-2：统一 length_normalize 双轨制
- [ ] P0-3：清理 3 个孤儿模板
- [ ] P0-4：修复 `_SafeDict` 静默失败

**交付物**：`directive-p-prompt-p0.md`（结构清理指令）
**验收**：600+ 测试通过，无功能变化

### 第二批（P1，3-5 天，质量提升）
- [ ] P1-1：升级 compose-v2（draft prompt）
- [ ] P1-2：升级 llm-audit-v2（audit prompt）
- [ ] P1-3：升级 plan-v2（plan prompt）
- [ ] P1-4：增强 truth_extract hook_updates（prompt 层，不改 schema）

**交付物**：`directive-p-prompt-p1.md`（内容升级指令）
**验收**：用 ch1-ch3 重新跑 audit 对比结果，验证新维度能发现问题

### 第三批（P2，后续迭代）
- P2-1~P2-4 工程化升级，待 10+ 章生产后再评估

---

## 六、风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| P1 升级后 prompt 变长，token 成本上升 | draft prompt 从 ~100 字 → ~600 字 | 在 200K 上下文下可忽略；且质量提升抵消成本 |
| 新维度可能导致 audit 过于严格 | 已生产章节可能被新维度判 critical | P1 验收时对比 ch1-ch3 audit 结果，调优 severity 阈值 |
| 钩子账本要求 plan 输出结构化 | 现有 plan 解析逻辑（`_extract_goal` 截断 50 字）需适配 | P1-3 同步更新解析逻辑 |
| 去 AI 味铁律过于严格 | 模型可能过度规避，影响表达自然度 | 铁律用"硬性禁令"（绝对）vs"铁律"（强约束）分级，给模型余地 |

---

## 附录：参考项目原文索引

### InkOS（核心借鉴）
- `storyforge/process/inkos-master (2)/inkos-master/packages/core/src/agents/writer-prompts.ts`
  - `buildCoreRules`（看点密集度 + 80/20 断章 + 去AI味铁律 + 硬性禁令）
  - `buildWritingCraftCard`（15 条写作铁律精简版，v10 实际注入版）
  - `buildCreativeConstitution`（14 条创作宪法）
  - `buildImmersionPillars`（6 大代入感支柱）
  - `buildGoldenOpeningDiscipline`（黄金三章）
- `.../continuity.ts` — Auditor 37 维度 + JSON schema + 评分校准
- `.../reviser.ts` — 双模式路由（PATCHES vs REVISED_CONTENT）
- `.../planner-prompts.ts` — Planner 7 段 memo + hook 账本 4 动作 + 揭1埋2

### snowflake-fiction（方法论知识库）
- `.../skills/chapter-write/references/writing-guide.md` — 9 参数模板 + Show Don't Tell 7 条 + 流水账自检
- `.../skills/novel-review/references/consistency-check-prompt.md` — 6 套一致性检查 + AI 痕迹清单
- `.../skills/hook-design/references/hook-types-and-criteria.md` — 5 类钩子 + 密度公式 + 4 阶段生命周期
- `.../skills/snowflake-fiction/references/million-word-webnovel-guide.md` — 黄金三章 + 爽点阶梯 + 番茄指标

### AI-Novel-Writing-Assistant（工程范式）
- `.../prompting/prompts/novel/chapterWriter.prompts.ts` — 8 条核心约束 + contextRequirements 优先级
- `.../prompting/prompts/audit/audit.prompts.ts` — light/full 双审 + category 白名单
- `.../services/audit/auditSchemas.ts` — fullAuditOutputSchema Zod 定义
- `.../docs/wiki/debugging/character-continuity-hard-facts.md` — 8 字段铁律
