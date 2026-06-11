# Codex 指令：Phase 5C-3 — 历史快照

> 发出日期：2026-06-08
> 产品经理：Claude Code PM
> 执行者：Codex
> 前置条件：Phase 5C-2 完成（322 tests, ruff clean, 11/11 Service Protocol 有对应实现）

---

## 任务概述

每次章节导出前自动创建 zip 快照，包含 chapters/ + truth/ + state/ 的完整状态。快照提供回滚能力和事后分析基础。

**目标**：导出操作不会丢失历史状态。任何章节导出前的完整 book 状态都可以恢复。

---

## 当前状态

### 已有基础设施

1. **`StoryForge3Config`** (`config.py`): pydantic-settings，新增配置项可自动从环境变量加载
2. **`_atomic_write_text()`** (`storage.py`): tmp + replace 原子写入模式
3. **`step_export()`** (`workflow.py:514-519`): 导出前不做任何状态保存
4. **`BookStorage`** (`storage.py`): 文件读写封装
5. **`ExportService`** (`services/export_service.py`): 单章和全书导出
6. **`PipelineLogger`** (`logging/pipeline_logger.py`): JSONL 审计日志（5C-1 已就位）

### 缺失

- 没有 `snapshots/` 目录管理
- 没有快照创建/清理逻辑
- 导出覆盖 chapters/ 和 truth/ 后无法回退
- Config 没有 snapshot 相关设置

---

## 修改目标

### 1. Config 扩展

**文件**：`src/storyforge3/config.py`

在 `StoryForge3Config` 新增两个字段：

```python
# ── Snapshots ──────────────────────────────────────────────
snapshot_enabled: bool = True
snapshot_max_count: int = 5
```

放在 `books_dir` 之后。

### 2. 新建 SnapshotManager

**文件**：`src/storyforge3/snapshot.py`（新建）

```python
from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path


class SnapshotManager:
    """导出前自动快照管理。"""

    def __init__(self, books_dir: str | Path, *, max_count: int = 5) -> None:
        self._books_dir = Path(books_dir)
        self._max_count = max(1, max_count)

    def create_snapshot(self, book_id: str, chapter_no: int) -> Path | None:
        """为指定书籍创建快照 zip。返回 zip 路径，无内容时返回 None。

        快照内容：
        - chapters/*.md
        - truth/*.json + truth.db（如果存在）
        - state/*.json（如果存在）
        - book.json, world.json, characters.json, volumes.json, context.md

        快照路径：{book_id}/snapshots/{timestamp}_ch{chapter_no:04d}.zip
        """
        book_dir = self._books_dir / book_id
        if not book_dir.exists():
            return None

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        snap_dir = book_dir / "snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)
        zip_path = snap_dir / f"{timestamp}_ch{chapter_no:04d}.zip"

        # 收集要打包的文件
        files_to_pack: list[tuple[Path, str]] = []  # (absolute, archive_name)
        for name in ("book.json", "world.json", "characters.json", "volumes.json", "context.md"):
            target = book_dir / name
            if target.exists():
                files_to_pack.append((target, name))

        for subdir in ("chapters", "truth", "state"):
            sub_path = book_dir / subdir
            if sub_path.exists():
                for child in sub_path.rglob("*"):
                    if child.is_file():
                        arc_name = f"{subdir}/{child.relative_to(sub_path)}"
                        files_to_pack.append((child, arc_name))

        # truth.db 在 book_dir 根目录（SQLite）
        truth_db = book_dir / "truth.db"
        if truth_db.exists():
            files_to_pack.append((truth_db, "truth.db"))

        if not files_to_pack:
            return None

        # 写入 zip（原子模式：先写 tmp，再 rename）
        tmp_path = zip_path.with_suffix(".zip.tmp")
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for abs_path, arc_name in files_to_pack:
                zf.write(abs_path, arc_name)
        tmp_path.replace(zip_path)

        # 快照元数据
        meta = {
            "book_id": book_id,
            "chapter_no": chapter_no,
            "timestamp": timestamp,
            "file_count": len(files_to_pack),
        }
        meta_path = zip_path.with_suffix(".meta.json")
        meta_tmp = meta_path.with_suffix(".meta.json.tmp")
        meta_tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        meta_tmp.replace(meta_path)

        # 清理旧快照
        self._cleanup(book_id)

        return zip_path

    def list_snapshots(self, book_id: str) -> list[dict]:
        """列出书籍的所有快照元数据，按时间倒序。"""
        snap_dir = self._books_dir / book_id / "snapshots"
        if not snap_dir.exists():
            return []
        results: list[dict] = []
        for meta_path in sorted(snap_dir.glob("*.meta.json"), reverse=True):
            try:
                results.append(json.loads(meta_path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                continue
        return results

    def _cleanup(self, book_id: str) -> None:
        """删除超出上限的旧快照（zip + meta.json 成对删除）。"""
        snap_dir = self._books_dir / book_id / "snapshots"
        if not snap_dir.exists():
            return
        zips = sorted(snap_dir.glob("*.zip"))
        while len(zips) > self._max_count:
            oldest = zips.pop(0)
            oldest.unlink(missing_ok=True)
            # 删除对应的 meta 文件
            oldest.with_suffix(".meta.json").unlink(missing_ok=True)
```

### 3. workflow.py 注入快照钩子

**文件**：`src/storyforge3/workflow.py`

在 `step_export` 调用前（当前第 211 行附近），添加快照创建：

```python
# 在 approve 状态记录之后、step_export 之前
if self.config.snapshot_enabled:
    self._create_snapshot(book_id, chapter_no)
```

新增方法：

```python
def _create_snapshot(self, book_id: str, chapter_no: int) -> None:
    """导出前创建快照。失败不阻塞主流程。"""
    try:
        from storyforge3.snapshot import SnapshotManager
        manager = SnapshotManager(self.config.books_dir, max_count=self.config.snapshot_max_count)
        manager.create_snapshot(book_id, chapter_no)
    except Exception:
        pass  # 快照失败不影响导出
```

### 4. 测试

**文件**：`tests/test_snapshot.py`（新建）

测试用例：

1. **`test_create_snapshot_zip_exists`**：创建快照后 zip 文件存在
2. **`test_create_snapshot_contains_chapters`**：zip 内包含 `chapters/0001.md`
3. **`test_create_snapshot_contains_truth`**：zip 内包含 `truth/` 目录文件
4. **`test_create_snapshot_metadata`**：meta.json 包含 book_id/chapter_no/timestamp/file_count
5. **`test_list_snapshots_ordered`**：创建 3 个快照，list_snapshots 按时间倒序
6. **`test_cleanup_removes_oldest`**：max_count=2，创建 3 个快照后只剩 2 个
7. **`test_cleanup_removes_paired_meta`**：删除 zip 时同时删除对应 meta.json
8. **`test_snapshot_empty_book_returns_none`**：空 book 目录返回 None
9. **`test_snapshot_nonexistent_book_returns_none`**：不存在的 book_id 返回 None
10. **`test_workflow_creates_snapshot_before_export`**：完整管线运行后 snapshots/ 目录存在且 zip 有效
11. **`test_snapshot_failure_does_not_block_export`**：mock SnapshotManager 抛异常，管线仍然 EXPORTED

---

## 技术约束

1. **快照失败不阻塞导出**：`_create_snapshot` 内 try/except，异常静默
2. **原子写入**：zip 先写 tmp 再 rename，避免写一半的损坏文件
3. **只用 stdlib**：`zipfile` + `json` + `pathlib` + `datetime`，不引入新依赖
4. **不改变现有测试**：322 测试必须全部通过
5. **不改变现有 API 契约**：不新增 API 端点
6. **Config 字段有默认值**：现有 .env 文件不受影响
7. **中文注释**：公共方法有 docstring

---

## 验收

```powershell
cd storyforge3
.\.venv\Scripts\python.exe -m pytest tests/ -q   # 322 + 新增测试通过
ruff check .                                       # clean
```

功能验收：
1. `config.snapshot_enabled` 和 `config.snapshot_max_count` 有默认值
2. 管线导出前 `snapshots/` 目录下生成 `{timestamp}_ch{chapter_no}.zip`
3. zip 包含 `chapters/` + `truth/` + `state/` + 根目录 JSON/MD
4. 对应 `.meta.json` 记录快照元数据
5. 超出 `snapshot_max_count` 时自动删除最旧快照（zip + meta 成对）
6. 快照失败不影响管线运行
7. 全部 322 + 新增测试通过

---

## 完成后回报格式

```
给 ClaudeCode 产品经理的执行结果：

Phase 5C-3（历史快照）：
- Config 扩展：[完成状态]
- SnapshotManager：[完成状态]
- workflow.py 钩子：[完成状态]
- 新增测试数：N
- 全量测试：[322+N] passed
- ruff check：[clean/有警告]
- 改动文件列表：[...]
```

---

## 参考文件

1. `src/storyforge3/config.py` — StoryForge3Config，新增 snapshot 字段
2. `src/storyforge3/workflow.py` — 管线主循环，注入快照钩子
3. `src/storyforge3/storage.py` — 原子写入模式参考
4. `src/storyforge3/logging/pipeline_logger.py` — JSONL 日志模式参考（非阻塞钩子）
