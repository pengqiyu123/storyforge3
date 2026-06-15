# 指令 P-FIX-1：修复 _truth_exists 门禁误判（get_status 不填充 truth → export 被拦）

> 下发 Codex。前置：P1-3（门禁）✅、P-DISCARD-1（discard）✅。
> 触发：PROD-1 生产审计发现——`chapter_service.py:get_status()` 不填充 `result.truth` 字段，导致 `_truth_exists()` 在 APPROVED 状态下返回 False，门禁误拦 export。当前因 `_advance_approve_state` 做双跳（AUDITED→APPROVED→TRUTH_COMMITTED）暂不触发，但门禁逻辑本身有缺陷——如果 approve 流程变化停在 APPROVED，export 将被永久阻塞。属 PM 缺陷全景报告 Bug A（P0 级隐患）。

## 背景

### 现状

1. `chapter_service.py:231-251` `approve()` 方法：读正文 → 提取 truth → 保存 truth → `_advance_approve_state()`（双跳 AUDITED→APPROVED→TRUTH_COMMITTED）→ 返回 `ChapterResult(truth=truth)`。**注意：approve() 返回的 result 有 truth 字段，但 get_status() 没有。**

2. `chapter_service.py:262-268` `get_status()` 方法：
   ```python
   async def get_status(self, book_id: str, chapter_no: int) -> ChapterResult | None:
       text = self.storage.read_text(self.paths.chapter_file(book_id, chapter_no))
       if text is not None:
           return ChapterResult(book_id, chapter_no, self._workflow_status(book_id, chapter_no), f"第{chapter_no}章", text)
       # ...
   ```
   **只读 text + status，不填充 truth 字段。**

3. `chapters.py:889-892` `_truth_exists()`：
   ```python
   def _truth_exists(result: ChapterResult | None) -> bool:
       if result is None:
           return False
       return result.truth is not None or _status_from_result(result) in {ChapterStatus.TRUTH_COMMITTED, ChapterStatus.EXPORTED}
   ```
   检查 `result.truth is not None` → 因 get_status 不填 truth → **永远 False**。fallback 检查 status in {TRUTH_COMMITTED, EXPORTED} → APPROVED 不在此集合 → **False**。

4. `gating.py:APPROVED` 行：
   ```python
   if chapter_status == ChapterStatus.APPROVED:
       actions = {"truth"}
       if truth_exists:
           actions.add("export")
       return frozenset(actions)
   ```
   truth_exists=False → export 不在允许集合 → **409 ACTION_NOT_ALLOWED**。

5. `chapters.py:572-574` approve 端点调用 `_guard_action(..., "approve", ...)`，approve 走完后 status 直接跳到 TRUTH_COMMITTED（双跳），**当前 ch2 不会卡在 APPROVED**。但这是脆弱依赖——如果流程变化（如 approve 和 truth 拆为两步、或 approve 失败但 truth 提取成功），状态可能停在 APPROVED，此时 export 被永久阻塞。

### 根因

`get_status()` 是唯一用于 API 状态查询的方法，但它不加载已持久化的 truth 数据。`_truth_exists()` 依赖 `result.truth` 字段但该字段永远不被 `get_status()` 填充。

## 任务

### 1. 修复 `_truth_exists()`（`src/storyforge3/api/routes/chapters.py`）

将 `_truth_exists()` 从仅检查 `result.truth` 字段扩展为**三重检查**：

```python
def _truth_exists(result: ChapterResult | None) -> bool:
    if result is None:
        return False
    # 1. result 本身带 truth（approve() 直接返回时）
    if result.truth is not None:
        return True
    # 2. 状态已是 truth_committed 或 exported（强信号）
    status = _status_from_result(result)
    if status in {ChapterStatus.TRUTH_COMMITTED, ChapterStatus.EXPORTED}:
        return True
    return False
```

> 注意：第二层检查已在当前代码中。**这一步实际上只是确认逻辑正确性**——当前代码的 fallback 已覆盖 TRUTH_COMMITTED/EXPORTED。关键问题在于 APPROVED 状态下 truth 文件可能已存在但状态未跳。见第 2 步。

### 2. 修复 `get_status()` 填充 truth（`src/storyforge3/services/chapter_service.py`）

`get_status()` 在返回 ChapterResult 时，如果状态为 TRUTH_COMMITTED 或 EXPORTED，应加载 truth 数据：

```python
async def get_status(self, book_id: str, chapter_no: int) -> ChapterResult | None:
    text = self.storage.read_text(self.paths.chapter_file(book_id, chapter_no))
    if text is not None:
        status = self._workflow_status(book_id, chapter_no)
        truth = None
        # 填充 truth：状态已达 truth_committed/exported 时从持久化加载
        if status in (ChapterStatus.TRUTH_COMMITTED, ChapterStatus.EXPORTED):
            truth = self.truth_store.load(book_id, chapter_no)
        return ChapterResult(book_id, chapter_no, status, f"第{chapter_no}章", text, truth=truth)
    if self._load_plan(book_id, chapter_no) is not None:
        return ChapterResult(book_id, chapter_no, ChapterStatus.PLANNED, f"第{chapter_no}章", "")
    return None
```

这样 `_truth_exists()` 的第一层检查 `result.truth is not None` 在 TRUTH_COMMITTED/EXPORTED 状态下也能命中。

### 3. APPROVED 状态下也检查 truth 文件（`src/storyforge3/api/routes/chapters.py`）

为了彻底覆盖"approve 流程变化导致停在 APPROVED"的场景，`_truth_exists()` 增加文件系统检查作为第三层 fallback：

```python
def _truth_exists(result: ChapterResult | None) -> bool:
    if result is None:
        return False
    if result.truth is not None:
        return True
    status = _status_from_result(result)
    if status in {ChapterStatus.TRUTH_COMMITTED, ChapterStatus.EXPORTED}:
        return True
    # APPROVED 状态：检查 truth 文件是否已持久化（容错：approve 双跳可能未完成）
    if status == ChapterStatus.APPROVED:
        return _truth_file_exists(result)
    return False
```

`_truth_file_exists` 需要访问 `TruthStore` 的路径。但 `_truth_exists` 是纯函数（无 service 注入）。**解决方案**：在 `_gate_state()` 中注入 truth_exists 判断，而非在 `_truth_exists` 中做文件检查：

```python
async def _gate_state(
    book_id: str,
    chapter_no: int,
    service: ChapterService,
    registry: RunRegistry,
) -> dict:
    get_status = getattr(service, "get_status", None)
    result = await get_status(book_id, chapter_no) if get_status is not None else None
    chapter_status = _status_from_result(result)
    audit_blocking = _audit_blocking_count(result, service)
    truth_exists = _truth_exists(result)
    # APPROVED 状态额外检查 truth 文件是否已持久化
    if not truth_exists and chapter_status == ChapterStatus.APPROVED:
        truth_store = getattr(service, "truth_store", None)
        if truth_store is not None:
            truth_exists = truth_store.load(book_id, chapter_no) is not None
    run_status = _current_run_status(registry, book_id, chapter_no)
    return {
        "chapter_status": chapter_status,
        "allowed": allowed_actions(chapter_status, run_status, audit_blocking, truth_exists),
    }
```

## Part 3：借鉴来源

| 借鉴 | 来源 | 方式 |
|------|------|------|
| `get_status()` 现有签名 | `chapter_service.py:262-268` | **扩展**（加 truth 加载） |
| `TruthStore.load()` | `truth/store.py:32-46` | **直接复用**（JSON 文件读取） |
| `_truth_exists()` 现有逻辑 | `chapters.py:889-892` | **扩展**（加 APPROVED fallback） |
| `_gate_state()` 现有流程 | `chapters.py:844-864` | **扩展**（注入 truth_store 检查） |

**新写比例**：约 **10%**。纯扩展既有函数，无新文件。

## 验收门禁

```powershell
.\.venv\Scripts\python.exe -m pytest --tb=short -q     # ≥589 不退步
.\.venv\Scripts\python.exe -m ruff check .               # clean
pnpm --dir web typecheck                                 # clean
```

手动（用 fixture 书）：
- 构造章节状态为 TRUTH_COMMITTED + truth 文件存在 → `get_status()` 返回的 result 有 truth 字段。
- 构造章节状态为 APPROVED + truth 文件存在 → `_gate_state()` 的 truth_exists=True → `allowed_actions` 包含 `export`。
- 构造章节状态为 APPROVED + truth 文件不存在 → truth_exists=False → `allowed_actions` 只有 `{"truth"}`。

## 必须覆盖的测试

- `get_status()` TRUTH_COMMITTED 状态返回 truth 数据（fixture 构造 truth JSON）。
- `get_status()` APPROVED 状态不加载 truth（truth 加载只在 TRUTH_COMMITTED/EXPORTED）。
- `_truth_exists()` TRUTH_COMMITTED → True（通过 status fallback）。
- `_truth_exists()` APPROVED + truth 文件存在 → True（通过 _gate_state 注入）。
- `_truth_exists()` APPROVED + truth 文件不存在 → False。
- `allowed_actions()` APPROVED + truth_exists=True → `{truth, export}`。
- `allowed_actions()` APPROVED + truth_exists=False → `{truth}`。

## 红线

- ❌ 不改 `allowed_actions()` 语义——它仍是纯函数，truth_exists 由调用方传入。
- ❌ 不改 `approve()` 流程——双跳机制保留。
- ❌ 不改 state machine TRANSITIONS。
- ❌ 不动《别打了》真实数据。
- ❌ 不做前端改动。

## 回报

- commit hash（建议 `fix(gating): populate truth in get_status and add APPROVED truth file fallback`）
- pytest + ruff 结果
- 测试中 APPROVED + truth_exists 的参数化用例列表

## Out of Scope

- ❌ Bug B 修复（resume_from 指向错误阶段，见 P-FIX-2）。
- ❌ ChapterStatus.SETTLED 清理（P-FIX-3）。
- ❌ spec §6 命名对齐（`run-full`/`truth-extract` 等，P2 文档级）。
- ❌ export hash 校验（spec 强制门禁缺失项，独立指令）。
