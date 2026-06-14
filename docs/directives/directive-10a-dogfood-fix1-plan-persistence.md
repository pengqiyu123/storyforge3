# Codex 指令：Dogfood Round 1 发现 #1 — Plan 步骤持久化

> 发出日期：2026-06-13
> 产品经理：Claude Code PM
> 执行者：Codex
> 前置条件：HEAD `854ec3a` + 未提交的 plan 显示/404 修复（前端 72 passed）
> 严重度：**P1（阻断 dogfood 续写流程）**
> 来源：Dogfood Round 1 真实用户反馈

## 一、问题现象

用户在 Web UI 对《别打了》第 2 章点击"规划"：

1. ✅ 后端 `POST /chapters/2/plan` 成功，返回 `goal + outline_node + arc_context + must_keep + must_avoid + style_emphasis`
2. ✅ 前端"本章规划"面板正确显示内容（Codex 已修复，72 passed）
3. ❌ **"规划"步骤没有打勾**（checkmark 不亮）
4. ❌ **刷新浏览器后，规划内容消失**

## 二、根因（PM 已完成代码审查，结论确定）

### 缺陷本质：`ChapterService.plan()` 是完全无状态操作

[chapter_service.py:73-79](src/storyforge3/services/chapter_service.py#L73-L79) 当前实现：

```python
async def plan(self, book_id: str, chapter_no: int) -> ChapterIntent:
    template = self.prompt_registry.get_latest("plan")
    prompt = self.prompt_registry.render_system_prompt(template, chapter_no=chapter_no)
    payload = {...}
    outline = await self.llm.generate_text("chapter_plan", prompt, payload, ...)
    goal = self._extract_goal(outline)
    return ChapterIntent(chapter_no, goal, outline_node=outline)  # ← 仅返回内存对象
```

**三个缺失**：

| 缺失 | 证据 | 后果 |
|------|------|------|
| ① plan 内容不落盘 | `StoragePaths` 无 `plan_file()` 路径 | 刷新即丢，无法复核 |
| ② plan 不推进状态机 | `plan()` 无 `state_machine.advance(..., PLANNED)` 调用 | checkmark 永不亮 |
| ③ `get_status()` 不识别 plan | [chapter_service.py:220-224](src/storyforge3/services/chapter_service.py#L220-L224)：无 chapter 文本即返回 `None` | API 返 404，前端 fallback empty |

### 设计不自洽的证据

`ChapterWorkflow.run()`（全管线）在 [workflow.py:84](src/storyforge3/workflow.py#L84) **会**推进状态到 `PLANNED`：

```python
self._advance(book_id, chapter_no, ChapterStatus.PLANNED)  # 全管线有，单步 plan 没有
plan = await self.step_plan(ctx, chapter_no)
```

**全管线**和**单步 plan 端点**对同一操作的处理不一致。单步端点漏了持久化与状态推进。

### `get_status()` 的 404 逻辑

[chapter_service.py:220-224](src/storyforge3/services/chapter_service.py#L220-L224)：

```python
async def get_status(self, book_id: str, chapter_no: int) -> ChapterResult | None:
    text = self.storage.read_text(self.paths.chapter_file(book_id, chapter_no))
    if text is None:        # ← 第 2 章无文本文件
        return None         # ← API 返 404 CHAPTER_NOT_FOUND
    return ChapterResult(...)
```

即使 plan 落盘、状态推进到 PLANNED，只要章节文本不存在，`get_status` 仍返回 `None` → 404。**必须扩展此方法识别"已规划未起草"状态**。

## 三、修复方案（PM 已定，Codex 照此实现）

**设计决策**：Plan 升级为**持久化的一等步骤**，与全管线行为对齐。这不是 bug 修补，是把缺失的持久化补齐，使单步操作与全管线自洽。

**定位（重要）**：这是**跨模式的数据正确性底线**，不是手动模式独有需求。无论 agent 调 `POST /run` 全管线、还是用户点单步按钮，只要生成了 plan，就必须落盘——可审计、可复用、run 失败时不必重新规划。`ChapterService.plan()` 是 service 层入口，一处改、全路径生效（单步端点 / 全管线 workflow / CLI 都经过）。豆包独立审查（`reviews/chapter-plan-persistence.md`）结论与本方案一致。

### 改动 1：存储路径 — `StoragePaths` 增加 `plan_file()`

[storage.py](src/storyforge3/storage.py) 的 `StoragePaths` 类，新增：

```python
def plan_file(self, book_id: str, chapter_no: int) -> Path:
    return self.book_dir(book_id) / "plans" / f"{chapter_no:04d}.json"
```

（参照现有 `chapter_file()` / `truth` 路径的命名风格）

### 改动 2：`ChapterService.plan()` — 落盘 + 推进状态

```python
async def plan(self, book_id: str, chapter_no: int) -> ChapterIntent:
    template = self.prompt_registry.get_latest("plan")
    prompt = self.prompt_registry.render_system_prompt(template, chapter_no=chapter_no)
    payload = {"book_id": book_id, "chapter_no": chapter_no, "context": self.storage.read_text(self.paths.context(book_id)) or ""}
    outline = await self.llm.generate_text("chapter_plan", prompt, payload, model=self.config.model_for_task("planner"))
    goal = self._extract_goal(outline)
    intent = ChapterIntent(chapter_no, goal, outline_node=outline)
    # ↓↓↓ 新增：落盘 + 状态推进
    self._persist_plan(book_id, chapter_no, intent)
    self._advance_plan_status(book_id, chapter_no)
    return intent
```

- `_persist_plan`：序列化 `ChapterIntent` 写入 `paths.plan_file()`（JSON，字段对齐 `_intent_to_response`）
- `_advance_plan_status`：调 `state_machine.advance(book_id, chapter_no, ChapterStatus.PLANNED)`
  - 注意：`EMPTY → PLANNED` 在 TRANSITIONS 中合法（[machine.py:15](src/storyforge3/state/machine.py#L15)），无需 force
  - 容错：若已是 PLANNED/DRAFTED 等更靠后状态，`advance` 会抛 `InvalidTransitionError`，**此时应跳过**（幂等：重复点规划不应报错）。参照 workflow.py 的 `_advance` 容错模式或直接 try/except `InvalidTransitionError` 后忽略

### 改动 3：`ChapterService.get_status()` — 识别已规划未起草

```python
async def get_status(self, book_id: str, chapter_no: int) -> ChapterResult | None:
    text = self.storage.read_text(self.paths.chapter_file(book_id, chapter_no))
    if text is not None:
        return ChapterResult(book_id, chapter_no, self._workflow_status(book_id, chapter_no), f"第{chapter_no}章", text)
    # ↓↓↓ 新增：无文本但有 plan → 返回 PLANNED
    if self.storage.read_text(self.paths.plan_file(book_id, chapter_no)) is not None:
        return ChapterResult(book_id, chapter_no, ChapterStatus.PLANNED, f"第{chapter_no}章", "")
    return None
```

**关键**：返回 `ChapterResult` 而非 `None`，这样 API 返 200 + `status=planned`，前端 checkmark 亮、不再 404。

### 改动 4：`ChapterService.draft()` — 复用已落盘 plan

[chapter_service.py:89](src/storyforge3/services/chapter_service.py#L89) 当前：

```python
intent = intent or await self.plan(book_id, chapter_no)  # 总是重新生成
```

改为优先读盘：

```python
intent = intent or self._load_plan(book_id, chapter_no) or await self.plan(book_id, chapter_no)
```

- `_load_plan`：读 `paths.plan_file()`，反序列化为 `ChapterIntent`，不存在返回 `None`
- **收益**：用户点"规划"复核后点"起草"，draft 复用同一份 plan，不再重复 LLM 调用（省时省钱、避免 plan 内容漂移）

### 改动 5：新增 `GET /chapters/{n}/plan` — 恢复端点（豆包审查缺口）

[api/routes/chapters.py](src/storyforge3/api/routes/chapters.py) 新增端点，返回已落盘的 ChapterIntent，供前端刷新后恢复"本章规划"面板：

```python
@router.get("/{chapter_no}/plan")
async def get_plan(book_id: str, chapter_no: int, service: ChapterService = Depends(get_chapter_service)):
    intent = service.load_plan(book_id, chapter_no)  # 复用改动4的 _load_plan 逻辑（提到 public）
    if intent is None:
        return ok(None)  # 未规划，返 200 + data=null（不要 404，前端用 null 判断）
    return ok(_intent_to_response(intent))
```

- **关键**：`GET /status` 只能返回 status 字段，返回不了 plan 内容（goal/outline/must_keep）。恢复 plan 内容面板必须靠这个端点
- 未规划时返 `200 + data=null`，不用 404（避免前端再处理 404 噪音）

### 改动 6：前端恢复 — `useChapterPlan` hook + ChapterPipeline 初始化（豆包方案）

**`web/src/hooks/useChapters.ts`** 新增：

```typescript
export function useChapterPlan(bookId: string, chapterNo: number) {
  return useQuery({
    queryKey: ["chapter-plan", bookId, chapterNo],
    queryFn: async () => {
      const res = await chaptersApi.getPlan(bookId, chapterNo);  // 新增 api 方法
      return res;  // 可能为 null
    },
    enabled: Boolean(bookId && chapterNo),
    staleTime: 0,  // plan 后需刷新
  });
}
```

**`web/src/api/chapters.ts`** 新增 `getPlan(bookId, chapterNo)` 调 `GET /chapters/{n}/plan`。

**`ChapterPipeline.tsx`** 用 hook 初始化 `lastPlan`，刷新后自动恢复：

```typescript
const { data: persistedPlan } = useChapterPlan(bookId, chapterNo);
const [lastPlan, setLastPlan] = useState<ChapterIntent | null>(persistedPlan ?? null);
useEffect(() => {
  if (persistedPlan) setLastPlan(persistedPlan);  // 落盘 plan 恢复
}, [persistedPlan]);
```

- **非阻塞恢复**：React Query 异步拉取，不阻塞组件渲染（豆包强调的"非阻塞恢复"）
- plan 成功后，`useQueryClient.invalidateQueries(["chapter-plan", ...])` 让缓存失效，下次拉到新 plan

## 四、验收标准（必须全过）

### 后端测试（pytest，目标 ≥6 新增）

1. `test_plan_persists_intent_file` — plan() 后 `paths.plan_file()` 存在且可反序列化
2. `test_plan_advances_status_to_planned` — plan() 后 `state_machine.current_status() == PLANNED`
3. `test_plan_is_idempotent` — 连续两次 plan() 不抛 `InvalidTransitionError`
4. `test_get_status_returns_planned_without_text` — plan 后无文本，`get_status()` 返回 `ChapterResult(status=PLANNED)`
5. `test_draft_reuses_persisted_plan` — draft() 时若 plan_file 存在，不重复调用 plan LLM（mock 计数验证）
6. `test_get_plan_endpoint_returns_persisted_intent` — `GET /chapters/{n}/plan` 返落盘 intent；未规划返 200+null

### 前端测试（vitest，目标 ≥1 新增）

1. `useChapterPlan restores persisted plan on mount` — mock GET /plan 返 intent，hook 挂载后 data 恢复
2. `ChapterPipeline shows plan panel after refresh` — persistedPlan 非空时渲染"本章规划"面板（即使没点过规划按钮）

### 全量回归

- `pytest --tb=no -q`：**501 + 新增，全绿**
- `ruff check .`：clean
- 状态机既有测试不回归（注意 `EMPTY → PLANNED` 已合法）

### 手动验收（PM 会做）

1. 重启后端
2. 点"规划"→ checkmark 亮
3. 刷新浏览器 → "本章规划"内容仍在 + checkmark 仍亮
4. 点"起草"→ draft 复用 plan，不再重复规划

## 五、范围红线（不要做）

- ❌ 不要改 plan prompt 模板
- ❌ 不要动全管线 `ChapterWorkflow.run()`（它本来就对，会自动受益于 service 层 plan 改动）
- ❌ 不要用 `beforeunload` / `localStorage` 当 plan 主存储（豆包明确反对，必须后端落盘为唯一真相源）
- ❌ 不要为 plan 恢复引入阻塞加载（用 React Query 非阻塞）
- ✅ checkmark 已基于 `result.status`，后端返 `planned` 后自动生效，前端步骤按钮逻辑**不用动**

## 六、交付

1. 实现代码改动 1-4
2. 新增后端测试 ≥5
3. `pytest` 全绿 + `ruff check .` clean
4. 提交 commit（conventional commits 格式）：
   `fix(chapter): persist plan intent and advance status to PLANNED (dogfood #1)`
5. 回报：改动文件清单、测试结果、commit hash

---

## PM 备注

这个修复会让 dogfood Round 1 的续写流程真正闭环。修复后请立即回报，PM 将重启后端让用户继续 draft → audit → revise → export 全链路。
