# 指令 P-DISCARD-1：章节 discard 原语（agent-mode 反向治理最小版）

> 下发 Codex。前置：P1-1b（reconcile）/ P-IMP-3b（validity）✅。可与 P1-3 并行，**不阻塞** dogfood。
> 触发：[`项目查缺补漏清单.md`](../项目查缺补漏清单.md) #1（PM 裁决 ELEVATE）。ch3/4 幽灵章节是 PM 手工 5 层 discard 才清掉的（truth.db 行 + truth JSON + exports + snapshots + pipeline.jsonl 行），证明"写错可安全丢弃重来"是**已发生**痛点。本指令把那次手写操作固化为有测试、可复用、强制备份的原语。

## 背景

agent-mode 下，agent 经 API 产章；产错/质量差需"清掉重产"。当前无任何删除端点——PM 清 ch3/4 时手工操作了 5 个数据层（且必须同时清 truth.db，否则 retriever 会把幽灵 truth 当上下文召回，污染重产）。手工不可持续，且易漏层。本指令提供统一的章节 discard 能力。

## 任务

### 1. `ChapterDiscarder` 服务（新 `src/storyforge3/services/chapter_discarder.py`）

丢弃一章的**全部产物**，覆盖 5 层（与 PM 手写一致）：

| 层 | 删除目标 |
|----|---------|
| 正文 | `chapters/{n:04d}.md` |
| 规划 | `plans/{n:04d}.json` |
| Truth JSON | `truth/chapter-{n:04d}.json` |
| **Truth DB** | `truth_entries` 中 `book_id=? AND chapter_no=?` 的**所有行**（关键——否则 retriever 污染重产） |
| 导出 | `exports/chapter-{n:04d}.*`（txt/md/epub，排除 `.tmp`） |
| 快照 | `snapshots/*ch{n:04d}*`（zip + meta） |
| Run 记录（新格式） | `chapters/{n:04d}/runs/` 整目录（若存在） |
| Run 记据（旧格式） | `runs/pipeline.jsonl` 中 `book_id=? AND chapter_no=?` 的行（**仅剥离该章**，保留其它章审计） |
| 状态 | `state/chapter_states.json` 中 `{book_id}:{n:04d}` 键（若存在） |

**强制安全**（红线级）：
- **先备份再删**：所有将删文件 + truth.db 该章行（导出为 JSON）→ 移入 `books/{book_id}/_trash/ch{n:04d}/`。**禁止静默物理删除**。
- **严格 scope**：仅 `(book_id, chapter_no)`；绝不跨章、绝不碰其它书。
- **不动 `book.json`**（`current_chapter` 保持；reconcile 从产物派生真相，UI 已不依赖 current_chapter）。
- **不动 `runs/pipeline.jsonl` 文件本身**（只剥离目标章行；其它章审计保留）。

**接口**：
```python
class ChapterDiscarder:
    def preview(self, book_id: str, chapter_no: int) -> DiscardPreview:
        """只读：列出将删文件 + truth.db 行数 + 将备份路径，无副作用。"""
    def discard(self, book_id: str, chapter_no: int) -> DiscardResult:
        """执行：备份→删除→返 summary（deleted_files/backed_up_to/truth_db_rows/post_reconcile）。"""
```

### 2. TruthStore 补 `delete_by_chapter`（`src/storyforge3/truth/store.py`）

不要在 discarder 里写裸 SQL。给 `TruthStore` 加方法：
```python
def delete_by_chapter(self, book_id: str, chapter_no: int) -> int:
    """参数化 DELETE，返回删除行数。仅删该 book+chapter。"""
```
discarder 调它。

### 3. API（`src/storyforge3/api/routes/chapters.py`）

两步（preview → confirm delete），agent-mode 友好：

- `GET /api/books/{book_id}/chapters/{chapter_no}/discard-preview` → `DiscardPreview`（文件清单 + truth_db 行数 + 备份路径），**无副作用**。
- `DELETE /api/books/{book_id}/chapters/{chapter_no}` → 执行 discard（备份+删除），返 `DiscardResult`（含 `post_reconcile` 刷新结果）。
  - **幂等**：章无产物时返回空 summary（不报错），便于 agent 安全重试。
  - 走统一 envelope `{ok, data, error}`。

> 不做 UI 按钮（agent-mode；agent/API 驱动）。CLI `storyforge3 discard-chapter {book} {n}` 可作薄包装（可选，复用 service）。

## Part 3：借鉴来源

| 借鉴 | 来源 | 方式 |
|------|------|------|
| 5 层删除目标 + 行为 | PM 手写 discard 脚本（清 ch3/4，已验证：92 truth.db 行 + 8 文件 + 14 pipeline.jsonl 行） | **直接固化** |
| 文件枚举 | `chapter_reconciler.py` `_numbered_files`/`_chapter_prefixed_files`/`_export_chapter_files`/`_chapter_no_from_prefixed_name` | **直接复用**（preview 枚举将删文件） |
| truth.db 访问 | `truth/store.py` `TruthStore` | **扩展**（加 `delete_by_chapter`） |
| pipeline.jsonl 行剥离 | `chapter_reconciler.py` `_legacy_run_chapters` 的行解析逻辑 | **模式复用**（同解析，改为剥离） |
| 备份/快照 | `snapshot.py` zip + meta 模式 | **模式复用** → `_trash/` 备份 |
| 状态机状态键格式 | `chapter_reconciler.py` `_state_statuses`（`{book_id}:{n:04d}`） | **直接复用** |
| 错误响应 | `api/errors.py` `ApiError` | **模式复用** |

**新写比例**：约 **40%**。新写 = discarder 编排 + preview + _trash 备份 + TruthStore.delete_by_chapter；扫描/truth/状态键/响应全复用既有。

## 验收门禁

```powershell
.\.venv\Scripts\python.exe -m pytest --tb=short -q     # ≥566 不退步
.\.venv\Scripts\python.exe -m ruff check .               # clean
pnpm --dir web typecheck                                 # clean（无前端改动，仅验不退步）
```

手动（**用测试 fixture 书，不动《别打了》**）：
- 构造一章含全部 5 层产物 → `discard-preview` 列出正确文件 + truth.db 行数，无副作用（文件仍在）。
- `DELETE` → `_trash/ch{n}/` 含全部备份；原 5 层全清；`post_reconcile` 该章消失，`max_chapter`/`valid_count` 正确下降。
- scope 安全：删 ch3 不动 ch2/ch4 任何产物。
- 幂等：对无产物章 DELETE 返空 summary，不报错。

## 必须覆盖的测试

- `ChapterDiscarder.preview`：枚举准确 + 无副作用（删除前后文件 hash 不变）。
- `ChapterDiscarder.discard`：5 层全清 + `_trash/` 备份完整 + truth.db 行归零。
- `TruthStore.delete_by_chapter`：仅删目标 book+chapter，其它章 truth 不动。
- pipeline.jsonl 剥离：仅移除目标章行，其它章行保留。
- scope 安全：删中间章不影响邻章。
- API：preview 无副作用；DELETE 幂等；envelope 格式；post_reconcile 字段正确。
- 用 `tests/test_chapter_reconciler.py` 同款 fixture 构造异常章，discard 后 reconcile 干净。

## 红线

- ❌ **禁止静默物理删除**——必须先备份到 `_trash/`。
- ❌ 严格 `(book_id, chapter_no)` scope——绝不跨章/跨书。
- ❌ 不动 `book.json`（current_chapter 保持）。
- ❌ 不删 `runs/pipeline.jsonl` 文件本身（只剥离目标章行）。
- ❌ 不做 UI 按钮 / 回收站 UI / 版本系统（agent-mode；API/CLI only；超出最小版）。
- ❌ 不做 trash 自动清理（手动后续）。
- ❌ 不动《别打了》真实数据（用 fixture 验证）。

## 回报

- commit hash（建议 `feat(discard): chapter discard primitive with mandatory trash backup`）
- pytest + ruff 结果
- 一次 fixture 书的 `discard-preview` + `DELETE` 输出（含 `_trash/` 备份清单 + post_reconcile）

## Out of Scope

- ❌ discard UI / 回收站 UI（#7 回收站，DEFER）。
- ❌ 批量 discard / discard 多章（单章原语先稳定）。
- ❌ trash 自动过期清理（手动）。
- ❌ 异常章节"修复"（补 state / 重生成正文）——#2，DEFER；本指令只做"丢弃"，不做"修复"。
- ❌ P1-3 门禁 / dogfood（独立轨道）。
