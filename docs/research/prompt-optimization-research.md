# StoryForge3 提示词优化调研报告

> PM 调研 | 2026-06-16
> 目的：(1) 建立 SF3 提示词基线；(2) 对比 5 个参考项目；(3) 汇总业界 2025-2026 最佳实践；(4) 输出优化建议。
> 后续：基于本报告 + SF2/SF3 对比，输出具体的提示词优化方案。

---

## 一、SF3 提示词现状基线（基线诊断）

### 1.1 关键发现：提示词未外部化

**`prompts/` 目录是空占位**。`prompts/system/.gitkeep` 和 `prompts/tasks/.gitkeep` 是空目录，设计意图是未来放外部 prompt 文件，目前未实现。所有提示词 **硬编码在 Python 代码** 里：

- **注册表单一真源**：`src/storyforge3/prompts/registry.py`（10 个模板）
- **散落内联 prompt**：`chapter_service.py`（draft）、`workflow.py`（patch revise）、`length_normalizer.py`（normalize）

**影响**：任何 prompt 调整都要改 Python 代码 + 重新部署，无热加载、无 A/B 测试、无版本对比。

### 1.2 SF3 10 个注册表模板清单

| task_type | prompt_id | 版本 | temperature | 是否真正被调用 |
|---|---|---|---|---|
| `compose` | compose-v1 | 1 | 0.85 | ✅ workflow.step_draft() |
| `plan` | plan-v1 | 1 | 0.5 | ✅ plan() |
| `truth_extract` | truth-extract-v2 | 2 | 0.2 | ✅ TruthExtractor.extract() |
| `audit` | audit-v1 | 1 | 0.3 | ❌ **孤儿模板**，无引用 |
| `revise` | revise-v1 | 1 | 0.75 | ✅ workflow.step_revise() rework 路径 |
| `llm_audit` | llm-audit-v1 | 1 | 0.2 | ✅ LLMAuditor.audit() |
| `length_normalize` | length-normalize-v1 | 1 | — | ❌ **未使用**，实际走内联 |
| `short_plan` | short-plan-v1 | 1 | 0.55 | ✅ 短篇规划 |
| `short_draft` | short-draft-v1 | 1 | 0.8 | ✅ 短篇起草 |

### 1.3 三个关键的"双轨制"问题

**问题 1：draft 有两套 system prompt**

| 路径 | 来源 | 内容 |
|---|---|---|
| `chapter_service.draft()` | 内联 `CHAPTER_DRAFT_PROMPT` 常量 | 7 条写作约束（场景推进/对话辨识/动作替代情绪/禁内心独白词/禁总结词/场景切换/禁工程术语） |
| `workflow.step_draft()` | 注册表 `compose-v1` | 5 条续写约束（承接上章/主角世界观连续/不新增设定/禁工程术语/只输出正文） |

**两套 prompt 风格不同**：内联版更详细（7 条具体写作技巧），注册表版更概括（5 条续写原则）。同一章节走不同路径产出风格不一致。

**问题 2：length_normalize 有两套**

| 路径 | 来源 |
|---|---|
| 注册表 `length-normalize-v1` | 未被使用 |
| `LengthNormalizer._prompt()` 内联 | `f"你是中文网文章节长度归一化编辑。请{verb}正文..."` |

**问题 3：`_SafeDict` 静默失败**

`render_system_prompt()` 使用 `_SafeDict`，**未定义的占位符会原样保留 `{xxx}` 输出给模型**，不报错。例如 `truth-extract-v2` 模板实际没引用 `{chapter_no}` 但仍传入——如果占位符拼错不会被发现。

### 1.4 SF3 核心提示词原文摘要

#### A. PLAN（plan-v1，temp 0.5）

```
你是中文网文章节规划师。
基于已有上下文，规划第{chapter_no}章的核心目标、冲突点和场景安排。
只输出章节计划（目标 + 关键情节点 + 预期节奏），不要输出章节正文。
保持与前章情节连续，不引入系统实现或工程术语。
只输出章节计划，不要输出正文。
```

**评价**：缺少结构化输出要求（goal/outline_node/must_keep 等字段如何对应？）、缺少爽点/钩子规划维度、缺少"揭1埋2"钩子账本概念。

#### B. DRAFT（compose-v1，temp 0.85）

```
你是中文网文续写作者，必须服务于既有小说。
续写第{chapter_no}章，必须承接上一章具体动作、信息或情绪余波。
保持主角、世界观、上一章事件连续；不跳时间，不跳场景，不重复上一章已写内容。
不新增无来源大设定、新势力或关键能力；必须由上下文给出的事实自然推出。
不要出现系统实现、工程术语或解释。
只输出章节正文。
```

**评价**：5 条约束偏"防御性"（不准做什么），缺少"建设性"指引（爽点密度、对话辨识度、Show Don't Tell、断章 80/20 法则）。对比 InkOS 的 25 条硬规则 + CreativeConstitution 14 条创作宪法，SF3 的 draft prompt 极度简陋。

#### C. LLM_AUDIT（llm-audit-v1，temp 0.2）

```
你是独立中文网文深度审计员，只输出结构化 JSON。
审计维度：OOC、战力一致性、信息边界、情节逻辑。
只报告章节文本与角色设定、世界规则、上一章 truth 的真实冲突。
不要重复机械规则问题，不要泛泛评价文笔。
输出 JSON object，字段为 issues；每个 issue 含 severity、dimension、description、suggestion。
```

**评价**：4 个维度偏少。对比 InkOS 的 37 个审查维度、snowflake 的 5 套独立检查（角色/时间线/设定/大纲/伏笔），SF3 缺少：钩子债务审计、节奏审计、爽点密度审计、AI 痕迹检测、伏笔回收追踪。

#### D. REVISE（revise-v1，temp 0.75）

```
你是中文网文修订编辑，当前修订模式是 {mode}。
只修复审计失败项：{failed_rules}
不得改变已确认的主角、事实、场景和章节承接。
{extra_constraints}
只输出修订后的章节正文。
```

**评价**：5 种模式（POLISH/SPOT_FIX/ANTI_DETECT/REWORK/SURGICAL）的 `extra_constraints` 设计良好，是 SF3 的亮点。但缺少"修订前/修订后对照"的元提示，模型容易过度修改。

#### E. TRUTH_EXTRACT（truth-extract-v2，temp 0.2）

```
你是中文小说 truth 提取器，只提取后续章节必须服从的事实。
必须严格输出 JSON object，字段名只能使用：fact_assertions, character_updates, relationship_updates, hook_updates, irreversible_facts, notes。
JSON schema: {...}
fact_assertions 是必填字段，必须是非空字符串数组；无法提取时也不能省略 fact_assertions。
只提取章节正文中真实发生、会影响后续连续性的事实，不要编造设定。
只输出符合 schema 的 JSON，不要 Markdown，不要解释。
```

**评价**：JSON schema 描述清晰，是 SF3 的另一个亮点。但 `hook_updates` 字段只要求 summary，缺少 hook 类型分类（开篇钩/章末钩/结构钩/悬念钩）和生命周期状态（埋设/推进/揭晓/余波）。

### 1.5 SF3 提示词的 5 个结构性缺陷

| # | 缺陷 | 影响 |
|---|---|---|
| D1 | **未外部化**，全部硬编码 Python | 无法热加载、A/B 测试、版本对比 |
| D2 | **双轨制**（draft/normalize 各两套） | 同章节走不同路径风格不一致 |
| D3 | **孤儿模板**（audit-v1、length-normalize-v1） | 维护负担，容易误用 |
| D4 | **`_SafeDict` 静默失败** | 占位符拼错不报错，prompt 带着 `{xxx}` 发给模型 |
| D5 | **缺乏网文工程化维度** | 无爽点密度、钩子账本、断章规则、AI 痕迹检测清单 |

---

## 二、5 个参考项目提示词设计对比

### 2.1 项目定位矩阵

| 项目 | 类型 | 提示词形态 | 网文工程化 | 一致性管理 | 多智能体 |
|---|---|---|---|---|---|
| **InkOS** | 工业级流水线 | TypeScript 内嵌 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **AI-Novel-Writing-Assistant** | 提示词工程平台 | PromptAsset 注册表 | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| **snowflake-fiction** | Claude 技能集 | Markdown SKILL | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ |
| **91Writing** | Vue 单体 | 内联字符串 | ⭐ | ⭐ | ⭐ |
| **SF3（当前）** | Python+React | Python 硬编码 | ⭐⭐ | ⭐⭐⭐ | ⭐⭐ |

### 2.2 InkOS（最完整工业化方案）

**核心机制**：
- **7 个 truth 文件**（JSON + Zod 校验）：current_state / particle_ledger / pending_hooks / chapter_summaries / subplot_board / emotional_arcs / character_matrix
- **Writer InputGovernanceContract**：限定 Writer 只能消费这些 truth 文件，禁止脑补
- **25 条硬规则 + 14 条 CreativeConstitution + 6 大 ImmersionPillars**

**网文工程化亮点**：
- 爽点密度：每 300 字 1 个爽点，每 500 字 1 个钩子
- 断章规则：80/20 法则（章末只兑现 20%，留 80% 悬念）
- 钩子账本：open / advance / resolve / defer 四种动作，"揭 1 埋 2"规则
- 去 AI 味铁律：明确黑名单句式（禁"不是…而是…"、禁"——"滥用）

**Auditor**：37 个编号审查维度，输出 JSON `{passed, overall_score, issues[], summary}`

**Reviser**：双模式自动路由（PATCHES 局部补丁 vs REVISED_CONTENT 全章重写）

### 2.3 AI-Novel-Writing-Assistant（最规范工程范式）

**核心机制**：
- **PromptAsset 注册表**：每个 prompt 是一个 asset，含 `id/version/taskType/mode/contextPolicy/outputSchema/render()`
- **强制规则**：禁止在 service 里直接写 systemPrompt，必须在 `prompts/<family>/*.prompts.ts` 注册
- **contextRequirements 优先级**（数字越大越不可丢）：
  ```
  book_contract=104 > chapter_mission=100 > character_hard_facts=99 
  > obligation_contract=99 > payoff_directives=98 > ...
  ```
  配合 `dropOrder` 决定 token 超限时按谁先裁

**工程亮点**：
- 全量 Zod schema 输出校验
- audit.category 白名单收敛（coherence/repetition/pacing/voice/engagement/logic）
- character_hard_facts 8 字段铁律（identityLabel/factionLabel/stanceLabel/powerLevel/realm/currentLocation/availability/prohibitions）

### 2.4 snowflake-fiction（最详方法论知识库）

**核心机制**：Claude skill 集，每个 skill 是一个 SKILL.md + references/*.md

**网文方法论亮点**：
- **黄金三章**：第1章开篇即冲突（3秒抓读者）/ 第2章世界观展开+金手指 / 第3章第一个爽点+打脸
- **爽点密度阶梯**：每3章小爽 / 每10章中爽 / 每30章大爽 / 每100章超大爽
- **5 类钩子 + 密度公式**：开篇钩（露一藏九）/ 章末钩（80/20）/ 结构钩（双灯塔）/ 悬念钩（信息不对称）/ 百花钩（6变体）
- **5 套一致性检查**（全输出 JSON）：角色一致性(6维) / 时间线(5维) / 设定一致性(5维) / 大纲偏离(5维) / 伏笔回收(4维，F[三位数字] ID 规则)
- **Show Don't Tell 三铁律**：禁直接陈述情绪 / 禁概述式叙事 / 禁贴标签式人物描写
- **AI 痕迹检测清单**：5 类 AI 高频词
- **番茄平台指标**：三章追读率 ≥35%、完读率 ≥15%

### 2.5 91Writing（反面对照样本）

所有提示词内联非结构化，`generateChapterContent` 仅取 `previousContent.slice(-500)`（最后500字）作为上下文。**几乎无一致性管理**，是"轻提示+拼字符串"流派，适合个人轻量使用，不适合长篇连载。

---

## 三、业界 2025-2026 最佳实践

### 3.1 从 Prompt Engineering 到 Context Engineering

2026 年的核心转变：**提示词工程 → 上下文工程**。

- 简单的 system prompt 已不够，关键在于 **RAG pipeline + memory architecture + evaluator 闭环**
- 长篇小说一致性的核心是 **story bible + character sheet + truth store** 的上下文管理
- 参考：[Reddit r/PromptEngineering 讨论](https://www.reddit.com/r/PromptEngineering/comments/1rci46t/prompt_engineering_is_dead_in_2026/)

### 3.2 六大提示词技术（K2view 2026）

| 技术 | 适用场景 | SF3 现状 |
|---|---|---|
| Zero-shot | 简单任务 | ✅ 大量使用 |
| Few-shot | 格式示范 | ❌ **几乎未用**（可在 JSON 输出 prompt 中加示例） |
| Chain-of-Thought | 复杂推理 | ❌ 未用（audit 可受益） |
| Meta prompting | 元任务分解 | ❌ 未用 |
| Self-prompting | 自我迭代 | ❌ 未用 |
| Context engineering | 长上下文管理 | 🔧 部分（ContextPackage 12000 字预算） |

### 3.3 中文网文 AI 写作方法论共识

业界（知乎/CSDN/飞书/GitHub skill 包）已形成成熟方法论：

```
黄金三章抓钩子 → 大纲分章控制爽点节奏 → 细纲填充反转 → 最终润色去AI味
```

**核心原则**：
- "套路 = 确定性的情绪满足"（oh-story-claudecode skill 包核心理念）
- "不要给读者出选择题"（snowflake-fiction）
- 去 AI 味的陷阱：①所有人共用一套去 AI 味提示词 → 产生新的同质化（AI味1.0→2.0）；②提示词一次性、不可复用

**参考资源**：
- [oh-story-claudecode](https://github.com/worldwonderer/oh-story-claudecode) — 网文 skill 包（扫榜/拆文/写作/去AI味/封面）
- [NinesAI 飞书知识库](https://docs.feishu.cn/article/wiki/TsShwKmo7ierrJkVWM6csF5MnRe) — 网文+AI 提示词知识大全
- [知乎：AI 写小说提示词](https://zhuanlan.zhihu.com/p/1972004501293593143) — 实操教程
- [Lakera AI 2026 提示词指南](https://www.lakera.ai/blog/prompt-engineering-guide)
- [Thomas Wiegold 2026 最佳实践](https://www.thomas-wiegold.com/blog/prompt-engineering-best-practices-2026/)

---

## 四、SF3 vs 参考项目：差距矩阵

| 维度 | SF3 现状 | InkOS | AI-Novel | snowflake | 差距 |
|---|---|---|---|---|---|
| **提示词外部化** | Python 硬编码 | TS 内嵌 | PromptAsset 注册表 | Markdown | 🔴 大 |
| **版本管理** | registry version 字段 | 无显式 | asset.version | 无 | 🟡 中 |
| **Context 优先级** | ContextPackage 6 block | InputGovernanceContract | contextRequirements 104→98 | 9 参数模板 | 🔴 大 |
| **爽点密度** | 无 | 300字1爽/500字1钩 | 无 | 3/10/30/100章阶梯 | 🔴 大 |
| **钩子账本** | truth.hook_updates（仅 summary） | open/advance/resolve/defer + 揭1埋2 | director.hookStrategy | 5类+密度公式+4阶段 | 🔴 大 |
| **断章规则** | 无 | 80/20 | 无 | 80/20 | 🔴 大 |
| **审计维度** | 4 维（OOC/战力/信息/逻辑） | 37 维 | 6 维+白名单 | 5套×5维 | 🔴 大 |
| **AI 痕迹检测** | 36 机械规则（部分） | 黑名单句式 | 禁止事项段 | 5类高频词清单 | 🟡 中 |
| **Truth 系统** | 6 字段 JSON schema | 7 文件+Zod | character_hard_facts 8字段 | F[数字]伏笔ID | 🟢 小（SF3 优势） |
| **修订模式** | 5 模式+extra_constraints | 双模式路由 | 无 | 无 | 🟢 小（SF3 优势） |
| **输出格式控制** | JSON schema（部分） | 混合 | 全量 Zod | JSON | 🟡 中 |
| **Few-shot 示例** | 无 | 无 | 无 | 无 | 🟡 中（业界都缺） |

---

## 五、优化方向初步建议（待 SF2 对比后细化）

### 5.1 P0：消除结构性缺陷（不改提示词内容）

1. **统一双轨制**：draft 统一到注册表（消除 `CHAPTER_DRAFT_PROMPT` 内联），normalize 同理
2. **清理孤儿模板**：删除或接入 `audit-v1`、`length-normalize-v1`
3. **修复 `_SafeDict`**：占位符未定义时抛错（严格模式）
4. **外部化基础设施**：接上 `prompts/system`、`prompts/tasks` 占位目录，支持文件覆盖

### 5.2 P1：增强网文工程化维度（改提示词内容）

5. **draft prompt 增加建设性约束**：
   - 爽点密度（每 300 字 1 爽点）
   - 断章规则（章末 80/20）
   - Show Don't Tell 三铁律
   - 对话辨识度（角色声音差异化）

6. **plan prompt 增加钩子规划**：
   - 本章埋设哪些钩子（类型 + 内容）
   - 本章回收哪些旧钩子
   - "揭 1 埋 2" 规则

7. **audit prompt 扩展维度**：
   - 钩子债务审计（未回收钩子清单）
   - 节奏审计（爽点密度是否达标）
   - AI 痕迹检测（黑名单句式扫描）

8. **truth_extract 增强 hook_updates**：
   - hook 类型分类（开篇钩/章末钩/结构钩/悬念钩）
   - 生命周期状态（埋设/推进/揭晓/余波）

### 5.3 P2：引入 Few-shot 和 CoT

9. **JSON 输出 prompt 加 few-shot 示例**：在 truth_extract / llm_audit 的 user payload 中注入 1-2 个正确输出示例
10. **audit 引入 Chain-of-Thought**：让模型先推理再下结论（"先列出章节中所有角色行动，再检查是否与 character profile 一致"）

---

## 六、下一步

本报告建立了 SF3 提示词基线 + 业界对比。接下来需要：
1. **对比 SF2 `process/` 目录**的参考项目提示词原文（特别是 InkOS Writer/Auditor/Reviser 完整 system prompt），提取可直接借鉴的片段
2. **输出具体的提示词优化方案文档**，按 P0/P1/P2 分级，每项给出"现状原文 → 优化后原文"的对照

---

## 附录：关键文件索引

### SF3 提示词相关文件
- `src/storyforge3/prompts/registry.py` — 提示词唯一真源（10 模板）
- `src/storyforge3/services/chapter_service.py` — 内联 `CHAPTER_DRAFT_PROMPT` + 各环节调用
- `src/storyforge3/workflow.py` — compose-v1 / revise-v1 / patch prompt + context package 拼装
- `src/storyforge3/truth/extractor.py` — truth_extract payload + schema
- `src/storyforge3/audit/llm_auditor.py` — llm_audit payload + schema
- `src/storyforge3/audit/revision_modes.py` — 5 种修订模式 + extra_constraints
- `src/storyforge3/services/length_normalizer.py` — 内联 length prompt
- `src/storyforge3/llm/llm_service.py` — LLM 层（不做 prompt 组装）
- `src/storyforge3/config.py` — 模型路由 `model_for_task`

### SF2 参考项目关键文件
- `storyforge/process/inkos-master (2)/inkos-master/packages/core/src/agents/writer-prompts.ts`
- `storyforge/process/inkos-master (2)/inkos-master/packages/core/src/agents/continuity.ts`
- `storyforge/process/inkos-master (2)/inkos-master/packages/core/src/agents/reviser.ts`
- `storyforge/process/inkos-master (2)/inkos-master/packages/core/src/agents/planner-prompts.ts`
- `storyforge/process/AI-Novel-Writing-Assistant/server/src/prompting/prompts/novel/chapterWriter.prompts.ts`
- `storyforge/process/AI-Novel-Writing-Assistant/server/src/prompting/prompts/audit/audit.prompts.ts`
- `storyforge/process/snowflake-fiction/skills/chapter-write/references/writing-guide.md`
- `storyforge/process/snowflake-fiction/skills/novel-review/references/consistency-check-prompt.md`
- `storyforge/process/snowflake-fiction/skills/hook-design/references/hook-types-and-criteria.md`
