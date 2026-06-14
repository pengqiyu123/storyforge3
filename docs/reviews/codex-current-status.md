# Codex 当前状态说明独立分析报告

> 评估对象：Codex 关于 StoryForge3 当前主线、P0.5 完成状态、P1-1 RunRecord 后端闭环、以及《别打了》项目数据状态的说明  
> 评估角色：Trae 独立分析师  
> 评估时间：2026-06-14

---

## 1. 总体结论

Codex 对当前项目阶段的判断总体正确：StoryForge3 已经从“按钮式手动章节管线”转向 **agent-mode first / agent-mode only 的运行查看模型**。P0.5 的核心目标是解除 dogfood 阻塞，P1-1 的核心目标是建立 RunRecord 后端最小闭环，这个阶段划分是合理的。

但 Codex 的说明中有三处需要特别校正或补充：

1. **“章节页改成纯查看模型”需要以当前代码实际状态为准**：文档和状态说明已锁定该方向，但前端是否完全移除所有运行按钮，需要以最终代码为准，不能只按描述认定。
2. **《别打了》数据状态存在明显不一致**：`book.json` 当前为 `current_chapter=2`，但项目目录已存在第 3、4 章的 truth/export/snapshot 等产物，说明受控元数据与运行产物不同步。
3. **P1-1 指令方向正确，但范围存在高风险**：它同时涉及模型、状态机、RunRegistry、异步 API、SSE 事件命名、resumable、truth/export 状态门禁，必须严格按“后端最小闭环”收口，不能扩展到完整前端 Run Viewer 或全量 Action Module。

最终判断：

> 当前项目可以进入 P1-1，但进入前必须先承认当前数据层存在“章节元数据与实际运行产物不一致”的事实，并将其作为 P1-1 RunRecord 的首个真实用例。P1-1 不应追求一次性完美恢复，而应先建立“可查询、可解释、可标记 resumable”的后端真相源。

---

## 2. 对 Codex 说法的逐项判断

### 2.1 “主线转向 agent-mode only”

判断：**方向成立。**

当前 `docs/current.md` 已明确写入：

- agent 模式唯一实现；
- 手动模式 deferred；
- Web UI 是只读 Run Viewer；
- 运行由 Claude Code / Codex / 外部 API 驱动。

这说明项目产品方向已经正式从“用户点击六步按钮”切换为“agent/API 驱动，前端观察”。

该转向是合理的，原因是：

- 章节管线耗时长，特别是 truth、draft、revise；
- 同步按钮式 UX 无法承载后台长任务；
- 自动导演后续必然要求可观察、可恢复的运行记录；
- 手动 UI 与 Agent 不应是两套流程，而应是同一套 Action/Run 的不同驱动方式。

但需要强调：

> agent-mode only 不等于“前端不重要”。前端从操作面板退居为 Run Viewer 后，状态可视化、错误解释、结果查看反而更关键。

---

### 2.2 “P0.5 已完成”

判断：**基本认可。**

Codex 列出的 P0.5 内容与 `docs/current.md` 大体一致，包括：

- SSE named-event 修复；
- status 200+empty；
- 分段流式正文；
- draft 状态推进到 DRAFTED；
- CCSwitch 供应商面板；
- 火山路由修复；
- CI 修复；
- dogfood 已推进《别打了》第 2 章。

从当前文档基线看：

- 后端 522 passed；
- 前端 82 passed；
- ruff clean；
- frontend build clean；
- Rust 本机未跑。

这些足以支持“P0.5 工程门禁通过”的结论。

但需要补充一个判断：

> P0.5 完成的是“dogfood 阻塞解除”，不是“运行系统完成”。当前仍然没有持久化 RunRecord，也没有真正意义上的断点恢复。

因此 P0.5 只能视为过渡层，不应继续在这个层面堆补丁。

---

### 2.3 “下一步进入 P1-1 RunRecord 后端最小闭环”

判断：**正确，而且优先级很高。**

P1-1 指令的目标非常明确：

> 刷新后前端能知道后台之前跑到哪。

这是当前项目最关键的架构缺口。没有 RunRecord，系统无法回答：

- 这次 run 是否仍在执行？
- 当前执行到哪个阶段？
- 哪个阶段失败？
- 能否恢复？
- 应从哪里恢复？
- 每阶段耗时多少？
- 当前章节产物状态与运行状态是否一致？

当前 `pipeline.jsonl` 已经记录了很多阶段日志，但它是 append-only 审计流，不是可查询的当前运行状态。P1-1 引入 `current_run.json` 和 `runs/{run_id}.json` 是必要的。

---

## 3. 《别打了》当前数据状态分析

### 3.1 book.json 与实际产物不一致

当前 `book.json` 显示：

```json
"current_chapter": 2
```

这与 Codex 说明一致。

但目录中已经存在：

- `truth/chapter-0003.json`
- `truth/chapter-0004.json`
- `exports/chapter-0003.txt`
- `exports/chapter-0004.txt`
- ch3/ch4 snapshot
- pipeline 日志中 ch3/ch4 full_pipeline success

这意味着：

```text
book.json 的 current_chapter = 2
但实际运行产物已经推进到第 4 章
```

这是一个明确的数据一致性问题。

### 3.2 chapter_states 也只记录到第 2 章

`chapter_states.json` 当前只记录：

- ch1 exported；
- ch2 approved。

没有 ch3/ch4 状态记录。

但 pipeline 日志显示 ch3 和 ch4 都已经成功 export。这说明：

> 运行日志、文件产物、章节状态、book meta 四者之间已经出现分裂。

这不是单纯“测试残留”这么简单，而是当前系统缺少统一 run/state reconciliation 机制的直接证据。

### 3.3 ch4 不是单纯残留，至少 pipeline 记录显示它完成过完整管线

pipeline 日志显示 ch4：

- plan 成功；
- draft 成功；
- audit 第一次 blocking=1；
- revise 成功；
- re-audit 通过；
- approve 成功；
- truth_extract 成功；
- export 成功；
- full_pipeline success。

这说明 ch4 产物不是随机文件，而是一次真实运行留下的完整产物。

但 ch4 的章节正文文件没有在当前 glob 结果中出现，只有 export/truth/snapshot。这需要后续核对：

- ch4 正文是否只存在 snapshot 或 export 中？
- 是否未写入 `chapters/0004.md`？
- 是否被 `.gitignore` 或文件移动影响？
- ChapterService 的写入状态是否和 export 使用的文本来源一致？

这应作为 P1-1 之前或 P1-1 过程中必须记录的异常样本。

---

## 4. P1-1 指令评估

### 4.1 指令方向正确

`directive-p1-1-runrecord.md` 的方向是正确的：

- 新增 `RunStatus`；
- 新增 `StageResult`；
- 新增 `PipelineRunRecord`；
- 新增 `RunRegistry`；
- 将 `POST /run` 改为异步立即返回 `run_id`；
- 增加 `GET /run`；
- 增加 resume/cancel；
- 运行中断后标记 `resumable`；
- 将 `APPROVED → TRUTH_COMMITTED → EXPORTED` 显式化。

这些都是解决当前问题的关键。

尤其是 `current_run.json` 的设计很重要。它让前端和 Agent 不必扫描整条 `pipeline.jsonl`，即可获取当前章节最近一次运行状态。

### 4.2 指令范围偏大，但仍可接受

P1-1 虽然称为“后端最小闭环”，但实际包含：

- 模型变更；
- 状态机变更；
- 新服务；
- API 行为变更；
- 后台任务；
- resumable；
- SSE 事件命名变更；
- truth/export 状态转移；
- 启动扫描。

这不是一个很小的任务。风险主要来自三点：

1. **`POST /run` 从同步改异步是行为级变更**。现有调用方和测试都需要适配。
2. **`TRUTH_COMMITTED` 会影响状态机、导出、已有 exported 数据兼容**。
3. **SSE 事件命名改为 `stage:*` / `run:*` 可能破坏 P0.5 刚修好的前端流式能力**。

因此执行时必须采用“加法兼容”原则：

- 后端可以新增 run/stage 事件；
- 但不能立刻删除旧 `pipeline:*` 事件，除非前端适配已经完成；
- exported 旧章节必须读时兼容；
- `POST /run` 如果返回结构变化，前端/API 客户端必须同步更新或保留兼容字段。

### 4.3 `resume` 在 P1-1 中应定义为“可标记、可入口”，不宜承诺完全续跑

P1-1 指令包含 resume endpoint。这个方向对，但需要控制预期。

当前真正的断点续跑涉及：

- 从 plan/draft/audit/revise/truth/export 哪个阶段恢复；
- 复用已有文本和 audit；
- 判断是否需要重新审计；
- 判断 truth 是否已提交；
- 避免重复导出；
- 防止覆盖已批准正文。

这不是 P1-1 必须完整解决的全部问题。

建议 P1-1 的 resume 定义为：

```text
P1-1：能识别 resume_from，并能返回可恢复状态。
P1-2/P1-3：逐步实现按阶段恢复执行。
```

否则 P1-1 容易膨胀。

---

## 5. 对 Codex 当前说明的关键风险判断

### 5.1 数据一致性风险：高

当前 `book.json`、`chapter_states.json`、`pipeline.jsonl`、truth/export 文件之间不一致。

风险表现：

- UI 可能显示 current_chapter=2；
- 后端 truth 已经包含 ch4；
- export 已有 ch4；
- 状态机不知道 ch4；
- AutoDirector 或 ContextRetriever 可能错误使用未来章节 truth。

这是非常关键的问题。尤其对小说连续性系统而言，未来章节 truth 泄漏到前面章节会严重污染上下文。

建议立即加入 P1-1 验收项：

> RunRecord / status reconciliation 必须能识别“存在产物但状态缺失”的章节，并至少报告为 inconsistent，而不是静默忽略。

### 5.2 truth 文件越界风险：高

Codex 已指出 truth 到 `chapter-0004.json` 需要核对。我的判断是：这不是小问题。

如果当前书籍 `current_chapter=2`，但 truth retriever 在生成第 3 章或第 2 章时可能读取到 ch4 truth，就会造成未来信息泄漏。

必须确认 TruthRetriever 的查询是否按 `chapter_no < current_chapter` 或目标章之前过滤。

建议增加测试：

```text
生成第 N 章上下文时，不得召回 chapter_no >= N 的 truth。
```

这比简单删除 ch4 文件更重要。

### 5.3 P1-1 改动影响面风险：中高

P1-1 会触及核心状态与 run 接口。风险包括：

- 现有 522 测试被状态机变更打破；
- `EXPORTED` 旧数据无法兼容 `TRUTH_COMMITTED`；
- 后台任务异常吞错；
- cancel/resume 语义不清；
- `current_run.json` 与实际 run 文件不同步。

建议所有 run state 写入采用：

```text
先写 run_id.json
再写 current_run.json 指针
失败时不得更新指针
```

### 5.4 前端说明与实现状态可能有偏差：中

Codex 表述“章节页改成纯查看模型”，而 `architecture/run-state-and-viewer.md` 中 P0.5 只说过渡态，P1 才整体换 Run Viewer。`docs/current.md` 则说章节页已纯 Run Viewer。

这三者存在细微差异。

建议 PM/Codex 在 P1-1 前统一术语：

- “纯查看模型”是已经上线，还是产品方向？
- P0.5 是否仍保留任何 run button？
- P1-2 的 Run Viewer 与当前章节页差异是什么？

如果不统一，验收时容易出现“文档说纯查看，代码还有按钮”的争议。

---

## 6. 对 P1-1 的建议收口版本

我建议 P1-1 严格收敛为以下最小闭环。

### 必做

1. 新增 RunStatus / StageResult / PipelineRunRecord。
2. 新增 RunRegistry。
3. 持久化 `runs/{run_id}.json`。
4. 持久化 `current_run.json`。
5. `POST /run` 立即返回 run_id。
6. `GET /run` 返回当前 run。
7. 后台任务至少能记录：start、stage_start、stage_complete、fail、complete。
8. 运行失败时写入 `resume_from`。
9. 服务启动扫描 running run，并标记为 resumable。
10. 保持 P0.5 SSE 流式能力不回归。
11. 后端测试与 ruff clean。

### 可以做，但不要扩大

1. `TRUTH_COMMITTED` 可以做，但必须读时兼容 exported 旧状态。
2. resume endpoint 可以先返回状态或做最小恢复，不要承诺完整阶段恢复。
3. cancel endpoint 可以先取消 registry 中活跃 task，重启后不保证取消已失效 task。

### 不应在 P1-1 做

1. 完整前端 Run Viewer。
2. 完整 Action Module。
3. 全流程门禁 UI。
4. 多 worker 队列。
5. 完整断点续跑策略。
6. 复杂数据迁移。

---

## 7. 对当前工作树风险的判断

Codex 提到：

> 根仓库有大量未提交删除/移动痕迹，不能乱回滚。

这个提醒非常重要。

建议：

1. P1-1 实施前先记录 `git status --short`。
2. 不做根仓库级别清理。
3. 不使用 destructive git 命令。
4. 只提交 StoryForge3 相关、明确属于 P1-1 的文件。
5. `book.json current_chapter=2` 属于运行数据变更，应明确是否提交；如果不是代码改动，不应混入 P1-1 代码提交。

当前 `book.json` 只有 `current_chapter` 从 0 到 2 的本地改动。如果这个文件属于 dogfood 受控数据，则可以单独提交；如果不是，应由 PM 明确是否纳入版本。

---

## 8. 对《别打了》当前章节状态的专业建议

当前《别打了》不应简单按 `current_chapter=2` 看待。更准确状态是：

```text
元数据进度：current_chapter=2
状态文件：ch1 exported，ch2 approved
运行日志：ch3 exported，ch4 exported
文件产物：ch3/ch4 truth/export/snapshot 存在
一致性：不一致，需要 reconciliation
```

建议 P1-1 完成后，第一件事不是继续写 ch5，而是运行一次“章节产物一致性检查”：

- 哪些 chapter 有正文？
- 哪些 chapter 有 plan？
- 哪些 chapter 有 truth？
- 哪些 chapter 有 export？
- 哪些 chapter 有 state？
- 哪些 chapter 有 pipeline run？
- 是否存在 truth/export 但无 state 的章节？
- 是否存在 state approved 但 truth 已存在/缺失？

这将直接验证 RunRecord 的价值。

---

## 9. 最终建议

### 9.1 是否进入 P1-1

建议：**可以进入。**

理由：

- P0.5 已解除关键 dogfood 阻塞；
- 当前 ch2/ch3/ch4 数据不一致正好证明 RunRecord 必要性；
- 继续生成章节会扩大不一致范围；
- P1-1 是 AutoDirector 前的必要底座。

### 9.2 进入 P1-1 的前置条件

进入前应确认：

1. 当前工作树状态已记录；
2. `book.json current_chapter=2` 是否提交由 PM 明确；
3. ch4 truth/export 是否为正式 dogfood 产物还是测试残留；
4. TruthRetriever 不会召回未来章节 truth；
5. P1-1 不扩展到完整前端 Run Viewer。

### 9.3 P1-1 验收重点

验收时必须看到：

1. `POST /run` 立即返回 run_id。
2. `GET /run` 能看到 running/current_stage。
3. 每阶段有 StageResult。
4. 失败时记录 error 和 resume_from。
5. 后端重启后 running run 被标记为 resumable。
6. P0.5 流式正文不回归。
7. 已 exported 旧章节兼容新状态机。
8. truth-before-export 仍生效。
9. pytest + ruff 通过。
10. 至少提供一次真实 run 的 JSON 输出。

---

## 10. 最终结论

Codex 的阶段判断总体正确：P0.5 已完成，下一步应进入 P1-1 RunRecord 后端最小闭环。

但当前项目不是一个“干净进入 P1-1”的状态，而是带着真实 dogfood 产生的数据不一致进入 P1-1：`book.json`、`chapter_states.json`、`pipeline.jsonl`、truth/export 文件之间已经分裂。这不是阻止 P1-1 的理由，反而是 P1-1 的最强理由。

最终建议：

> 批准 Codex 进入 P1-1，但要求严格收口为后端 RunRecord 最小闭环，并把《别打了》当前 ch2/ch3/ch4 的不一致状态纳入验收样本。P1-1 的目标不是立刻完美续跑，而是让系统第一次拥有”我知道自己跑到哪里、哪里失败、能否恢复”的事实层。

---

# 产品经理综合判断（Claude Code PM）

> 身份：Claude Code PM（本项目专职产品经理，负责需求拆解、指令下发、验收）
> 判断时间：2026-06-14
> 评估对象：Trae 独立分析报告（§1-§10）
> 方法：独立核验关键事实 + 风险点修正 + 决策收口

## A. 对 Trae 报告的总体评价

| 维度 | 评分 | 依据 |
|------|------|------|
| **数据来源可靠性** | ⭐⭐⭐⭐⭐ | 引用的 book.json / chapter_states.json / pipeline.jsonl / 目录产物均经我独立核验属实，无臆测 |
| **方法论科学性** | ⭐⭐⭐⭐☆ | 逐项判断 + 风险分级 + 收口建议结构完整；唯一短板是 truth 泄漏风险（§5.2）未读源码验证，属推测 |
| **结论合理性** | ⭐⭐⭐⭐⭐ | “数据不一致是 P1-1 最强动机”的核心论点精准，收口版本（§6）可直接采纳 |
| **增量价值** | ⭐⭐⭐⭐☆ | 独立指出 ch3/ch4 产物分裂问题，是 Codex 报告未涉及的盲区 |

**总判断**：Trae 报告质量高，结论可信，收口建议可直接作为 P1-1 执行边界。但有**一个高风险点需要修正降级**，且我发现了**一个 Trae 未充分展开的更严重异常**（见 §C）。

## B. 我的独立核验结果（PM 实地查证）

我逐项核验了 Trae 的数据不一致论断，结果**全部属实**，且异常图景比 Trae 描述的更完整：

| 章节 | 正文 000X.md | chapter_states | truth 000X.json | export 000X.txt | snapshot |
|------|:---:|:---:|:---:|:---:|:---:|
| ch1 | ✓ | exported | ✓ | ✓ | — |
| **ch2** | ✓ | **approved** | ✓ | **✗ 缺失** | — |
| **ch3** | **✗ 缺失** | **✗ 缺失** | ✓ | ✓ | ✓ ch0003.zip |
| **ch4** | **✗ 缺失** | **✗ 缺失** | ✓ | ✓ | ✓ ch0004.zip |

`book.json.current_chapter = 2`

**这证实了 Trae §3 的”四层分裂”判断**：元数据 / 状态机 / 文件产物 / 运行日志之间已经不一致。

## C. 关键发现（对 Trae 报告的修正与补充）

### C1.【修正·降级】truth 未来章节泄漏风险：高 → 低（需补防御测试）

Trae §5.2 将”truth retriever 召回未来章节”列为**高风险**。我读源码核验：`truth/retriever.py:49/56/64` 的过滤条件是**严格 `entry.chapter_no < chapter_no`**（小于，非小于等于），逻辑上生成第 N 章时**不会召回 chapter_no >= N 的 truth**。

> **修正**：当前代码无泄漏 bug。风险降级为”低”，但需补一条防御性测试断言（见 §F），防止未来重构破坏该不变量。Trae 此处是基于担忧的合理推测，非已证实的缺陷——其建议增加测试的方向仍正确。

### C2.【补充·升级】ch3/ch4 是”幽灵章节”——比 Trae 描述更严重

Trae §3.3 疑问”ch4 正文是否只在 snapshot”。我核验：**ch3/ch4 正文文件、chapter_states 记录全部缺失，但 truth/export/snapshot 齐全**。这不是”测试残留”，而是：

- snapshot 在 export 前创建（`snapshot.py` 已知行为）→ ch3/ch4 确实跑过 export 流程
- 但正文 + 状态记录双双消失 → 说明这些产物来自**一次 ChapterService 写入异常或更早 book 版本/不同 book_id 的运行**，事后正文被清理而 truth/export/snapshot 留存
- **更怪的是 ch2**：state=approved + 有 truth，但**无 export**——而 ch3/ch4 反而有 export。这个”倒挂”（靠后的章有 export，靠前的章反而没有）无法用”顺序推进”解释

> **补充判断**：这正是 RunRecord 缺失的最坏实证——系统连”这些产物从哪次运行、哪个 book_id 来的”都回答不了。Trae 的”reconciliation 检查”建议（§8）应**升级为 P1-1 的硬验收项**，不是可选 follow-up。

### C3.【认同】resume 收口 + 工作树保护

完全认同 Trae §4.3（resume 只做”可标记可入口”）和 §7（不乱回滚根仓库）。这两条直接采纳为 P1-1 约束。

## D. 决策

### 批准进入 P1-1 ✅

理由与 Trae §9.1 一致，并强化：当前 ch2/ch3/ch4 的”幽灵章节 + 倒挂 export”是 RunRecord 缺失的活体证据，**继续生成 ch5 只会扩大分裂**，P1-1 必须立即启动。

### 附带约束（在 Trae §6 收口版本基础上，我增加 3 条）

**采纳 Trae §6 全部边界**（必做 11 项 / 可做 3 项 / 不做 6 项），并增加以下 PM 约束：

| 约束 | 来源 | 说明 |
|------|------|------|
| **① reconciliation 为硬验收项** | PM（升级 Trae §8） | P1-1 必须能识别”有产物但无 state”的章节并报告 inconsistent，ch3/ch4 作为验收样本 |
| **② truth retriever 防御测试** | PM（修正 Trae §5.2） | 新增测试：生成第 N 章时 truth 召回集合中不得含 chapter_no >= N，防止未来回归 |
| **③ book.json current_chapter=2 不混入 P1-1 提交** | Trae §7 + PM | 该改动是 dogfood 运行数据，非代码；Codex 提交 P1-1 时须排除此文件或单独提交 |

## E. 对工作树与数据状态的处置指令（给 Codex）

1. **P1-1 实施前**：`git status --short` 存档，不做根仓库清理，不用 destructive git 命令。
2. **ch3/ch4 幽灵章节**：**P1-1 期间不删不改**，作为 reconciliation 的真实样本。是否清理留待 P1-1 验收后由 PM 决定。
3. **book.json current_chapter**：保持现状（=2），不回退不前进，等 P1-1 RunRecord 落地后由系统 reconciliation 重新认定真实进度。
4. **提交边界**：P1-1 commit 只含 RunRecord 相关代码 + 测试，`book.json` 运行数据变更单独提交或暂不提交。

## F. P1-1 验收重点（PM 最终清单）

在 Trae §9.3 的 10 项基础上，我定稿为以下 PM 验收清单：

1. `POST /run` 立即返 run_id（<50ms，不挂）
2. `GET /run` 返回 running + current_stage + stage_results
3. 后端重启后 running run → resumable（不假装无损）
4. P0.5 流式正文（llm:chunk）不回归
5. APPROVED→TRUTH_COMMITTED→EXPORTED 转移合法；EXPORTED 旧数据读时兼容
6. truth-before-export 守卫不回归
7. **【新增】reconciliation 能识别 ch3/ch4 这类”有产物无 state”章节并报告 inconsistent**
8. **【新增】truth retriever 测试断言：召回集合 chapter_no 严格 < 目标章**
9. 522 后端基线不退步 + ruff clean
10. 一次完整 run 的 `GET /run` JSON 输出

## G. 后续行动

| 顺序 | 行动 | 责任 |
|------|------|------|
| 1 | 本判断报告已下发，P1-1 指令（含我补的 Part 3 借鉴来源 + 本报告约束）交 Codex 执行 | PM |
| 2 | Codex 执行 P1-1，遵守 Trae §6 收口 + PM §D 三约束 | Codex |
| 3 | P1-1 完成后 PM 按 §F 清单验收，重点核 reconciliation + truth 防御测试 | PM |
| 4 | 验收通过后下发 P1-2（前端 Run Viewer 最小版） | PM |

---

**PM 结论**：Trae 的分析扎实可信，唯一一处风险评级（truth 泄漏）经源码核验应降级；同时我发现”ch3/ch4 幽灵章节 + ch2 export 倒挂”这一比 Trae 描述更严重的实证。**批准进入 P1-1，附带 Trae §6 收口边界 + PM 三约束（reconciliation 硬验收 / truth 防御测试 / book.json 不混提交）。** RunRecord 不是锦上添花，而是当前数据分裂的唯一解药。
