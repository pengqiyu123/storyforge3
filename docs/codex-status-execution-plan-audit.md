# Codex 项目状态分析与执行计划审计意见

> 审计对象：Codex 关于 `truth timeout`、`plan persistence`、后续测试与 dogfood 恢复顺序的状态分析和执行计划。  
> 审计方式：静态代码核对为主，辅以一次针对性测试尝试。  
> 结论级别：当前后端处于 **不可重启稳定态**，必须先收口 `plan persistence` 半成品，再继续 dogfood。

---

> ⚙️ **PM 综合裁决（2026-06-13，Claude Code PM 补充，合并豆包意见）**
>
> 三方一致：豆包静态审查 + PM 运行时核实 + dogfood Round 1 实测，结论收敛——**后端当前不可稳定重启，`plan persistence` 是 P0 半成品**。Codex 主线判断正确，执行顺序合理。
>
> **PM 对豆包意见的 4 点增量/修正：**
>
> 1. **truth timeout 600s 有运行时佐证**：dogfood Round 1 实测 `truth_extract` 耗时 **402.5s**（weShareAi relay hold，`in/out=None`），第 2 章因此 120s 超时失败、第 3 章提至 600s 后成功 exported。**600s 独立超时是必要的、非过设**。Codex 此项设计（独立 `llm_truth_timeout_seconds`、不污染 default=120）优于 PM 原议"提 default"，认可。
> 2. **前端恢复 = P1，但禁止留半成品**：结合 agent-mode-first pivot，dogfood 走 curl 全管线、前端是只读 viewer，plan 面板刷新恢复非阻断——故前端恢复列 P1（与豆包 §8 一致）。**但**：现状 `useChapterPlan(bookId)` 已在 `useChapters.ts:44` 定义、被 `ChapterPipeline.tsx:46` 调用，却**签名缺 `chapterNo`**、`chapters.ts` **无 `getPlan`**、后端无 `GET /plan`——这是**悬空半成品调用**。P0 阶段必须二选一：要么完整做前端恢复，要么回退该调用让前端回到不报错的 lastPlan 内存态。**不允许保留当前悬空状态。**
> 3. **`GET /plan` 端点升 P0**：plan 落盘是跨模式数据底线（agent `POST /run` 全管线内部 plan 也经 service 层落盘），`GET /plan` 是 agent/MCP/前端读取入口。豆包 §3.5 已识别，PM 确认升 P0（豆包 §8 列在后端 P0 清单第 5 项，定位正确）。
> 4. **提交纪律**：truth timeout 与 plan persistence 改动文件不重叠（前者 config/client/factory/llm_service + 3 测试，后者 storage/chapter_service/chapters.py + web），**分两个 commit**，隔离已验证增量，便于回滚。
>
> **执行顺序**：先 commit truth timeout（已验证落袋）→ 收口 plan persistence 后端 P0（B1-B5）+ 决定前端去留（任务 C 二选一）→ 全量回绿 → 重启后端继续 dogfood。**完整收口清单见文末 §11。**

---

## 1. 总体结论

Codex 对当前局面的主判断是正确的：

> 应先完成 `plan persistence` 功能线，整合已经基本完成的 `truth timeout 600s` 修改，然后一次性跑通后端测试，再重启后端继续 dogfood。

原因很明确：当前代码里 `truth timeout` 修改相对完整，但 `plan persistence` 已经进入半实现状态，且有明确运行时崩溃路径。此时如果直接重启后端或继续 Web dogfood，点击“规划”大概率会触发后端 500，导致 dogfood 数据不可信，甚至阻断整个章节续写流程。

本轮状态应定性为：

```text
truth timeout：基本完成，等待全量测试确认
plan persistence：危险半成品，必须立即收口
后端整体：不稳定，不应继续 dogfood
前端 dogfood：应暂停，等待后端恢复可重启基线
```

风险等级：**P0 阻断级**。

---

## 2. `truth timeout` P0 任务完成状态评估

### 2.1 已完成内容

从当前代码看，`truth timeout` 的核心修改已经到位。

#### 配置项已新增

位置：[config.py](file:///D:/python/Novel/storyforge3/src/storyforge3/config.py#L11-L14)

当前配置包含：

```python
llm_timeout_seconds: int = 120
llm_draft_timeout_seconds: int = 300
llm_truth_timeout_seconds: int = 600
llm_short_timeout_seconds: int = 60
```

这满足“新增独立配置项 `llm_truth_timeout_seconds=600`”的要求。

#### LLMClient 已仅对 truth_extract 使用 600 秒

位置：[client.py](file:///D:/python/Novel/storyforge3/src/storyforge3/llm/client.py#L203-L211)

当前逻辑为：

```python
if "draft" in normalized or "revise" in normalized or "normalize" in normalized:
    return self.config.llm_draft_timeout_seconds
if normalized == "truth_extract":
    return self.config.llm_truth_timeout_seconds
if normalized == "health":
    return self.config.llm_short_timeout_seconds
return self.config.llm_timeout_seconds
```

这说明：

- `truth_extract` 使用 600 秒；
- `chapter_plan` 仍走默认 120 秒；
- `draft/revise/normalize` 仍走 300 秒；
- `health` 仍走 60 秒。

任务边界清楚，没有把所有 LLM 调用都粗暴拉长。

#### LLMService 已接入 truth_timeout

位置：[llm_service.py](file:///D:/python/Novel/storyforge3/src/storyforge3/llm/llm_service.py#L85-L99) 和 [llm_service.py](file:///D:/python/Novel/storyforge3/src/storyforge3/llm/llm_service.py#L608-L615)

`LLMService` 构造函数已接收：

```python
truth_timeout: int = 600
```

任务超时分发也已包含：

```python
if normalized == "truth_extract":
    return self.truth_timeout
```

#### factory 已注入配置

位置：[factory.py](file:///D:/python/Novel/storyforge3/src/storyforge3/llm/factory.py#L26-L32)

`create_llm_service()` 已将 `config.llm_truth_timeout_seconds` 注入 `LLMService`。

#### 测试已覆盖配置与任务分发

现有测试已包含：

- [test_config.py](file:///D:/python/Novel/storyforge3/tests/test_config.py#L7-L27)：默认值和环境变量覆盖；
- [test_llm_client.py](file:///D:/python/Novel/storyforge3/tests/test_llm_client.py#L182-L195)：`truth_extract == 600`；
- [test_llm_service.py](file:///D:/python/Novel/storyforge3/tests/test_llm_service.py#L313-L323)：`truth_extract` 走 600 秒。

### 2.2 完成度判断

`truth timeout` 可评为：**功能实现 90%+ 完成**。

剩余不确定性主要不是设计问题，而是全量测试尚未完全确认。

### 2.3 剩余 2 个 chapter service 测试未完成的影响

如果 Codex 报告的“后端全量测试剩余 2 个 chapter service 测试未完成”属实，那么影响不应归因于 `truth timeout` 本身，而应主要归因于 `plan persistence` 半成品。

当前 `truth timeout` 相关代码路径较独立，不会自然导致 chapter service 测试失败。相反，当前 `ChapterService.plan()` 已调用未实现 helper，明显会破坏 chapter service 测试。

因此判断：

```text
truth timeout 修改本身可以保留；
剩余 chapter service 测试失败不应阻止 truth timeout 方案；
但必须在 plan persistence 收口后重新跑全量测试，才能合并为稳定基线。
```

---

## 3. `plan persistence` 半成品状态风险分析

### 3.1 当前代码存在明确崩溃路径

位置：[chapter_service.py](file:///D:/python/Novel/storyforge3/src/storyforge3/services/chapter_service.py#L73-L82)

当前 `plan()` 已经调用：

```python
self._save_plan(book_id, intent)
self._advance_planned_state(book_id, chapter_no)
```

但在同一文件后续没有看到 `_save_plan()`、`_load_plan()`、`_advance_planned_state()` 的实现。文件底部只到 `_should_chunk_draft()` 和 `_content_fingerprint()`，见 [chapter_service.py](file:///D:/python/Novel/storyforge3/src/storyforge3/services/chapter_service.py#L464-L470)。

这意味着：

```text
调用 ChapterService.plan()
  -> LLM 生成 outline 成功
  -> 构造 ChapterIntent 成功
  -> 调用 self._save_plan(...)
  -> AttributeError
  -> API 500 / 流程中断
```

这是 P0 级别问题。

### 3.2 StoragePaths 仍没有 plan 文件路径

位置：[storage.py](file:///D:/python/Novel/storyforge3/src/storyforge3/storage.py#L35-L46)

当前存在：

- `chapter_file()`；
- `truth_file()`；
- `export_file()`；
- `chapter_states()`。

但没有：

```python
def plan_file(self, book_id: str, chapter_no: int) -> Path:
    ...
```

因此即使补 `_save_plan()`，也还缺少统一路径定义。

### 3.3 `draft()` 尚未复用 persisted plan

位置：[chapter_service.py](file:///D:/python/Novel/storyforge3/src/storyforge3/services/chapter_service.py#L87-L96)

当前逻辑仍是：

```python
intent = intent or await self.plan(book_id, chapter_no)
```

它没有执行 Codex 计划中要求的优先级：

```text
passed intent -> persisted plan -> generate new plan
```

这会导致两个问题：

1. 用户已经点过“规划”后，再点“起草”仍可能重新调用 planner；
2. 如果后端重启后前端不传 intent，draft 不会读取已保存 plan，而是重新生成。

在当前半成品状态下，问题更严重：如果 `intent is None`，`draft()` 会调用 `plan()`，而 `plan()` 现在会因 `_save_plan` 缺失崩溃。

### 3.4 `get_status()` 尚未识别 planned-only 状态

位置：[chapter_service.py](file:///D:/python/Novel/storyforge3/src/storyforge3/services/chapter_service.py#L226-L230)

当前逻辑：

```python
text = self.storage.read_text(self.paths.chapter_file(book_id, chapter_no))
if text is None:
    return None
return ChapterResult(...)
```

这意味着：

- 只有 plan 文件、没有正文时，状态仍会返回 `None`；
- 前端无法知道该章节已经 planned；
- 刷新后即使 plan 文件存在，状态也不会恢复为 `planned`。

这与 Codex 目标“refresh still shows the plan and the checkmark”不一致。

### 3.5 API 读取 plan 端点尚未恢复

位置：[chapters.py](file:///D:/python/Novel/storyforge3/src/storyforge3/api/routes/chapters.py#L318-L325)

当前只有：

```python
@router.post("/{chapter_no}/plan")
```

没有：

```python
@router.get("/{chapter_no}/plan")
```

这意味着刷新后前端没有后端读取入口。

### 3.6 前端仍依赖 lastPlan 内存状态

位置：[ChapterPipeline.tsx](file:///D:/python/Novel/storyforge3/web/src/components/chapters/ChapterPipeline.tsx#L45-L55) 和 [ChapterPipeline.tsx](file:///D:/python/Novel/storyforge3/web/src/components/chapters/ChapterPipeline.tsx#L290-L333)

当前规划面板仍依赖：

```typescript
const [lastPlan, setLastPlan] = useState<ChapterIntent | null>(null);
```

刷新后 `lastPlan` 初始化为 `null`，面板消失。

这说明即使后端 plan 保存完成，如果前端不接 `GET /plan`，刷新后规划内容仍无法恢复。

---

## 4. Codex 执行顺序审查

Codex 建议顺序：

```text
先完成 plan persistence 线
  -> 整合 truth timeout 600s 修改
  -> 一次性通过后端全量测试
  -> 重启后端继续 dogfood
```

### 4.1 合理性判断

该顺序合理，且应该严格执行。

原因：

1. 当前 `plan()` 已经处于会崩溃的半实现状态；
2. dogfood 依赖规划、起草、状态恢复；
3. truth timeout 虽然重要，但它不阻塞后端启动；
4. plan persistence 半成品会直接导致 API 500；
5. 如果此时继续 dogfood，得到的是“坏基线”数据。

### 4.2 可行性判断

该顺序可行，改动面集中在：

- [storage.py](file:///D:/python/Novel/storyforge3/src/storyforge3/storage.py)；
- [chapter_service.py](file:///D:/python/Novel/storyforge3/src/storyforge3/services/chapter_service.py)；
- [chapters.py](file:///D:/python/Novel/storyforge3/src/storyforge3/api/routes/chapters.py)；
- chapter service / API tests；
- 前端 plan query 和恢复测试。

其中后端收口是必须项，前端恢复是完成用户问题的必要项。

### 4.3 执行顺序需要微调的地方

建议把 Codex 的顺序细化为：

```text
1. 先修后端编译/运行时崩溃：plan_file、_save_plan、_load_plan、_advance_planned_state
2. 修 draft 复用 persisted plan
3. 修 get_status planned-only
4. 补 GET /plan
5. 跑 targeted chapter service + API tests
6. 跑全量后端测试 + ruff
7. 再接前端 useChapterPlanState 和刷新恢复
8. 跑前端 targeted tests
9. 重启后端继续 dogfood
```

如果时间很紧，至少必须先完成 1-6，再重启后端；否则后端不可用。

---

## 5. 实现收口方案是否能达成稳定后端版本

Codex 建议的实现收口项包括：

- `plan_file`；
- `_save_plan`；
- `_load_plan`；
- `_advance_planned_state`；
- `get_status planned`；
- `draft` 复用；
- 修复 chapter service 失败测试；
- 保留 `truth_extract=600s`。

### 5.1 可以达成稳定后端版本，但有前提

这些项如果完整实现，可以达成“可重启的稳定后端版本”。

稳定后端的最低标准是：

1. `POST /plan` 不崩；
2. `plan()` 结果原子落盘；
3. `GET /plan` 能读回；
4. `GET /status` 在只有 plan、无正文时返回 `planned`；
5. `POST /draft` 在无 request intent 时优先读保存 plan；
6. 保存过的 plan 在后端重启后仍可复用；
7. 全量后端测试通过；
8. ruff 通过。

### 5.2 必须注意的实现细节

#### 5.2.1 plan JSON 应直接映射 ChapterIntent

P0 阶段可以先保存 `ChapterIntent` 原始 shape：

```json
{
  "chapter_no": 2,
  "goal": "...",
  "outline_node": "...",
  "arc_context": "...",
  "must_keep": [],
  "must_avoid": [],
  "style_emphasis": []
}
```

这足够支撑：

- 刷新恢复；
- draft 复用；
- Agent/MCP 读取；
- 后端重启不丢。

用户勾选状态和备注可以作为 P1，不应阻塞本次 P0 后端恢复。

#### 5.2.2 `_advance_planned_state` 必须幂等

应只在状态为空时推进到 `PLANNED`。

如果章节已经 `DRAFTED`、`AUDITED`、`REVISED`、`EXPORTED`，不应倒退。

#### 5.2.3 `draft()` 的优先级必须严格测试

目标顺序：

```text
显式传入 intent
  -> 已保存 plan
  -> 新生成 plan
```

必须新增测试断言：当 plan 文件存在且 draft 入参为 `None` 时，不再调用 `chapter_plan` LLM。

#### 5.2.4 `get_status()` 不应把 planned-only 当作章节正文

`planned` 状态应返回 `text=""`，但前端必须知道这是“已规划、未起草”，不能误认为空章节可编辑。

---

## 6. 本地验证说明

我尝试运行针对性测试：

```powershell
python -m pytest tests/test_chapter_service.py -q
```

但当前本地环境缺少 `ebooklib`，pytest 在加载插件阶段失败：

```text
ModuleNotFoundError: No module named 'ebooklib'
```

因此本次无法独立复现 Codex 所称“仅剩 2 个 chapter service 测试失败”。

但从静态代码审查可以确认：当前 `ChapterService.plan()` 调用了未实现 helper，这是确定性运行时错误，不依赖测试环境。

---

## 7. 当前项目状态判断

### 7.1 状态分级

| 模块 | 当前状态 | 风险 |
|---|---|---|
| truth timeout | 基本完成 | 中低 |
| plan persistence 后端 | 半成品，会崩溃 | P0 |
| plan persistence API | 未闭环 | P0/P1 |
| plan persistence 前端恢复 | 未闭环 | P1 |
| dogfood 后端稳定性 | 不满足 | P0 |
| 全量测试可信度 | 待恢复 | P0 |

### 7.2 当前是否可以继续 dogfood

不建议。

原因：

- 点击规划可能直接 500；
- draft 在无 intent 时也会走崩溃路径；
- status 不识别 planned-only；
- 刷新恢复仍不完整；
- dogfood 结果会被半成品污染。

应先恢复后端稳定基线。

---

## 8. 推荐执行计划

### P0：立即收口后端

1. 在 [storage.py](file:///D:/python/Novel/storyforge3/src/storyforge3/storage.py) 增加 `plan_file()`。
2. 在 [chapter_service.py](file:///D:/python/Novel/storyforge3/src/storyforge3/services/chapter_service.py) 实现：
   - `_save_plan()`；
   - `_load_plan()`；
   - `_advance_planned_state()`；
   - 可选 `_bump_current_chapter()`。
3. 修改 `draft()`：
   - `intent = intent or self._load_plan(...) or await self.plan(...)`。
4. 修改 `get_status()`：
   - 无正文但有 plan 时返回 `ChapterStatus.PLANNED` 和空文本。
5. 在 [chapters.py](file:///D:/python/Novel/storyforge3/src/storyforge3/api/routes/chapters.py) 增加：
   - `GET /api/books/{book_id}/chapters/{chapter_no}/plan`。
6. 补后端测试：
   - plan 落盘；
   - get_plan 读回；
   - status planned-only；
   - draft 复用 plan；
   - repeated plan 不倒退状态。

### P0：验证门禁

必须通过：

```powershell
python -m pytest tests/test_chapter_service.py -q
python -m pytest tests/api/test_chapters.py -q
python -m pytest --tb=no -q
ruff check .
```

如果本地缺依赖，应先使用项目标准环境或安装缺失依赖，否则测试结论不可信。

### P1：前端恢复闭环

1. [chapters.ts](file:///D:/python/Novel/storyforge3/web/src/api/chapters.ts) 增加 `getPlan()`。
2. [useChapters.ts](file:///D:/python/Novel/storyforge3/web/src/hooks/useChapters.ts) 增加 `useChapterPlanState()`。
3. [ChapterPipeline.tsx](file:///D:/python/Novel/storyforge3/web/src/components/chapters/ChapterPipeline.tsx) 使用 persisted plan 初始化展示。
4. 补刷新恢复测试。

### P2：勾选状态和用户输入持久化

这不是当前后端崩溃修复的必要前提，但属于原始用户需求的完整闭环。后续应设计 `ChapterPlanState` 和 `PATCH /plan`。

---

## 9. 对 Codex 方案的最终审计意见

### 9.1 正确之处

Codex 建议的主线是正确的：

- 不应继续 dogfood；
- 应先完成 plan persistence；
- truth timeout 600s 修改应保留；
- 最终以全量测试和 ruff 作为恢复门禁；
- 后端重启后再继续真实创作验证。

### 9.2 需要补强之处

Codex 方案需要明确：

1. 当前不是“还差测试”，而是存在确定性运行时崩溃；
2. `_save_plan()` / `_advance_planned_state()` 缺失是 P0；
3. `draft()` 不复用 `_load_plan()` 会导致重启后不能复用规划；
4. `GET /plan` 和前端 query 是刷新恢复的必要条件；
5. 勾选状态和用户输入持久化不应混入本次 P0 后端救火，但必须进入后续 P1/P2。

---

## 10. 最终判断

当前项目不应被视为“truth timeout 只差两个测试”的轻微未完成状态，而应视为：

> `truth timeout` 基本完成，但 `plan persistence` 半实现已经破坏章节规划运行路径，后端当前不具备稳定重启和继续 dogfood 的条件。

建议立即执行 Codex 的收口路线，但要按 P0 后端稳定优先级推进：

```text
实现 plan_file / _save_plan / _load_plan / _advance_planned_state
  -> draft 复用 persisted plan
  -> get_status 支持 planned-only
  -> GET /plan
  -> 修复 chapter service/API 测试
  -> 保留 truth_extract=600s
  -> 全量 pytest + ruff
  -> 重启后端
  -> 继续 dogfood
```

只有完成以上步骤，项目才重新回到“可重启、可 dogfood、可继续 Phase 10B 前置验证”的稳定状态。

---

## 11. PM 收口指令（下发 Codex，合并豆包 §3/§5/§8/§9 意见 + PM 核实）

> 本节为豆包审计 + PM 运行时核实合并后的**权威收口清单**。Codex 照此执行，完成后回报。前三节（PM 综合裁决 / 豆包 §1-§10）为本清单的支撑依据。

### 任务 A — truth timeout（已完成，先落袋）

单独 commit：`fix(llm): give truth_extract its own 600s timeout (dogfood #4)`

范围：`config.py` / `client.py` / `factory.py` / `llm_service.py` + `test_config.py` / `test_llm_client.py` / `test_llm_service.py`。此项 Codex 已完成 90%+（豆包 §2 确认），补全测试后**单独提交**，先固化 P0 根因（dogfood 实测 402.5s 坐实必要）。

### 任务 B — plan persistence 后端收口（P0，阻断 dogfood）

对齐 `directive-10a-dogfood-fix1-plan-persistence.md` + 豆包 §3/§5 + PLAN.md。

**B1 StoragePaths**（[storage.py](src/storyforge3/storage.py)）：新增
```python
def plan_file(self, book_id: str, chapter_no: int) -> Path:
    return self.book_dir(book_id) / "plans" / f"{chapter_no:04d}.json"
```

**B2 ChapterService helpers**（[chapter_service.py](src/storyforge3/services/chapter_service.py)）：实现 4 个（当前 plan() L80-81 / get_plan() L84-85 已调用，仅缺定义）
- `_save_plan(book_id, intent)`：序列化 ChapterIntent（shape 见豆包 §5.2.1）原子写入 `plan_file`
- `_load_plan(book_id, chapter_no)`：反序列化，不存在返 `None`
- `_advance_planned_state(book_id, chapter_no)`：幂等，仅 `EMPTY→PLANNED`，已 `PLANNED+` 跳过不 force（豆包 §5.2.2）
- （可选）`_bump_current_chapter`：`current_chapter = max(existing, chapter_no)`，注释写明语义 = "触达最高章节"非"完成章节"（豆包评估 §5）

**B3 draft 复用**（[chapter_service.py:95](src/storyforge3/services/chapter_service.py#L95)）：
```python
intent = intent or self._load_plan(book_id, chapter_no) or await self.plan(book_id, chapter_no)
```
豆包 §5.2.3：必须测试 plan_file 存在 + `intent=None` 时**不重调 `chapter_plan` LLM**。

**B4 get_status**（[chapter_service.py:226-230](src/storyforge3/services/chapter_service.py#L226)）：无正文但有 plan_file → `ChapterResult(status=PLANNED, text="")`，不再 `None→404`。豆包 §5.2.4：planned 返 `text=""`，前端须知是"已规划未起草"不可当空章节编辑。

**B5 API GET /plan**（[chapters.py](src/storyforge3/api/routes/chapters.py)）：新增 `GET /{chapter_no}/plan`，返落盘 intent；未规划 `200 + data=null`（**不要 404**，避免前端噪音）。复用 `service.get_plan()`。

### 任务 C — 前端去留决策（P0 阶段必须二选一，禁止留半成品）

现状：`useChapterPlan(bookId)` 已存在于 [useChapters.ts:44](web/src/hooks/useChapters.ts#L44) 且被 [ChapterPipeline.tsx:46](web/src/components/chapters/ChapterPipeline.tsx#L46) 调用，但**签名缺 `chapterNo`**、[chapters.ts](web/src/api/chapters.ts) **无 `getPlan`**、后端无 `GET /plan`。悬空。

- **选项 1（推荐，agent-mode-first 下最快恢复 dogfood）**：P0 先**回退** ChapterPipeline 对 `useChapterPlan` 的调用 + 移除该 hook，前端回到 lastPlan 内存态（不报错）。前端完整恢复作为 **P1 单独任务**。
- **选项 2**：P0 直接完整做前端恢复（`getPlan` api + `useChapterPlan(bookId, chapterNo)` 签名修正 + ChapterPipeline 用 persistedPlan 初始化 + 刷新恢复测试，非阻塞 React Query）。

Codex 选其一并回报。**不允许保留当前悬空状态。**

### 验收门禁（必须全过）

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_chapter_service.py -q
.\.venv\Scripts\python.exe -m pytest tests/api/test_chapters.py -q
.\.venv\Scripts\python.exe -m pytest --tb=no -q      # 501 + 新增，全绿
.\.venv\Scripts\python.exe -m ruff check .             # clean
（选 C-选项2 时）cd web; pnpm test; pnpm build
```

> 注：豆包 §6 本地缺 `ebooklib` 导致 pytest 加载失败。Codex **必须用项目 venv**（`.venv\Scripts\python.exe`）跑测试，确保依赖齐全，否则测试结论不可信。

### 后端新增测试 ≥7

plan 落盘 / 状态推进 PLANNED / 幂等（重复 plan 不崩不倒退）/ get_status 返 planned / draft 复用不重调 plan LLM（mock 计数）/ GET /plan 返 intent（未规划 200+null）/ current_chapter 更新。

### 提交（conventional commits，分 2 个）

1. `fix(llm): give truth_extract its own 600s timeout (dogfood #4)`
2. `fix(chapter): persist plan intent and advance status to PLANNED (dogfood #1/#3)`

（选 C-选项2 时，前端并入 #2 或单独 #3）

### 红线

- ❌ 不改 plan prompt 模板、不动全管线 `workflow.run()`（它本就对，自动受益于 service 层改动）
- ❌ plan 主存储不用 localStorage/beforeunload（后端落盘为唯一真相源，豆包 §5.1）
- ❌ 不留前端半成品悬空调用（任务 C 二选一）
- ❌ 不在缺依赖环境跑测试下结论（用项目 venv）

### 回报

改动文件清单 / 新增测试数 / `pytest` + `ruff` 结果 / 2 个 commit hash / 任务 C 所选选项。

完成后 PM 将重启后端验证三件事：① 点规划 → plan 落盘 + 状态推进 PLANNED ② `GET /plan` 读回 intent ③ draft 复用落盘 plan、不重新调用 planner。三件通过即恢复 dogfood。
