# P-LIFECYCLE-0：书籍归档/删除 + 导出文件清理

> 指令编号：P-LIFECYCLE-0
> 下发时间：2026-06-16
> 下发人：ZCode（PM）
> 执行人：Trae / Codex
> 优先级：P0

---

## 1. 问题陈述

当前产品的数据生命周期存在基础断裂：**书创建了就永远存在，没有任何删除或归档路径**。唯一的"删除"是 `workspace restore`（整个工作区核弹式重建），这根本不是正常操作。

导出文件同样没有清理能力——重导出覆盖同名文件，不同格式的旧文件永久残留。

这不是高级功能缺失，是**产品基础操作闭环没形成**。在补全这些之前，所有生产、迭代、dogfood 都在"没有退路"的状态下进行。

---

## 2. 目标

### 2.1 书籍归档/删除

提供两个层级的"去掉一本书"能力：

- **归档**（`PATCH /books/{book_id}/status` → `archived`）：软操作，标记书不再活跃，列表默认不显示
- **删除**（`DELETE /books/{book_id}`）：硬操作，备份全书数据到 `_trash` 后从主目录移除

### 2.2 导出文件清理

- **删除单个导出**（`DELETE /books/{book_id}/exports/{filename}`）
- **批量清理**（`DELETE /books/{book_id}/exports`，清除全部导出文件）

---

## 3. 改动范围

### 3.1 书籍归档（改动最小）

**文件**：`src/storyforge3/models.py` + `src/storyforge3/api/routes/books.py`

**models.py** — `BookStatus` 枚举加 `ARCHIVED`：
```python
class BookStatus(str, Enum):
    INCUBATING = "incubating"
    OUTLINING = "outlining"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    DROPPED = "dropped"
    ARCHIVED = "archived"  # 新增
```

**books.py** — `list_books` 默认过滤 `archived`：
```python
@router.get("")
async def list_books(
    include_archived: bool = False,  # 查询参数，默认 False
    service: BookService = Depends(get_book_service),
):
    books = await service.list_books()
    if not include_archived:
        books = [b for b in books if b.status != BookStatus.ARCHIVED]
    return ok([_meta_to_response(book) for book in books])
```

归档本身不需要新端点——现有的 `PATCH /books/{book_id}/status` 已支持，只需枚举值可用。归档的书仍然可以通过 `GET /books/{book_id}` 单独访问。

### 3.2 书籍删除

**新建文件**：`src/storyforge3/services/book_discarder.py`
**修改文件**：`src/storyforge3/api/routes/books.py`、`src/storyforge3/api/deps.py`、`tests/`

**book_discarder.py** — 参照 `chapter_discarder.py` 的备份模式：

```python
class BookDiscarder:
    """书籍级删除，备份全书数据到 _trash 后移除。"""

    def preview(self, book_id: str) -> BookDiscardPreview:
        """预览将被删除的文件列表和统计。"""

    def discard(self, book_id: str) -> BookDiscardResult:
        """
        执行步骤：
        1. 检查书籍状态（不允许删除 ACTIVE 状态有未导出章节的书）
        2. 全量备份到 books_root/_trash/{book_id}_{timestamp}/
           - 备份内容：book.json, context.md, world.json, characters.json,
             relationships.json, volumes.json, chapters/, truth/, exports/,
             state/, plans/, runs/, snapshots/, diagnostics/
        3. 清理 truth.db 中该书的条目（如果有跨书 truth.db）
        4. shutil.rmtree(book_dir)
        5. 返回 DiscardResult（含备份路径、文件统计）
        """

    def restore(self, book_id: str, backup_id: str) -> BookMeta:
        """
        从 _trash 恢复书籍。将备份目录复制回 books_root/{book_id}/。
        返回恢复后的 BookMeta。
        """
```

**books.py** — 新增两个端点：

```python
@router.delete("/{book_id}")
async def delete_book(
    book_id: str,
    discarder: BookDiscarder = Depends(get_book_discarder),
):
    """硬删除书籍，备份到 _trash。"""

@router.get("/{book_id}/delete-preview")
async def delete_book_preview(
    book_id: str,
    discarder: BookDiscarder = Depends(get_book_discarder),
):
    """预览删除影响，不执行。"""

@router.post("/_trash/{backup_id}/restore")
async def restore_book(
    backup_id: str,
    discarder: BookDiscarder = Depends(get_book_discarder),
):
    """从 _trash 恢复书籍。"""
```

**安全约束**：
- 不允许删除状态为 `active` 且有 `DRAFTED/AUDITED/NEEDS_REVISION/REVISED` 状态章节的书（提示先导出或 discard 章节）
- `exported` 和 `empty` 状态的书可以删除
- `completed` 状态的书可以删除
- `archived` 状态的书可以删除
- 备份目录结构：`{books_root}/_trash/{book_id}_{YYYYMMDD_HHMMSS}/`

### 3.3 导出文件清理

**修改文件**：`src/storyforge3/api/routes/export.py`

```python
@router.delete("/exports/{filename}")
async def delete_export(
    book_id: str,
    filename: str,
    paths: StoragePaths = Depends(get_paths),
):
    """删除单个导出文件。带路径遍历防护（同现有 download）。"""
    export_dir = (paths.book_dir(book_id) / "exports").resolve()
    path = (export_dir / filename).resolve()
    if not _is_within(path, export_dir) or not path.is_file():
        raise ApiError(status=404, code="EXPORT_NOT_FOUND", message=f"Export not found: {filename}")
    path.unlink()
    return ok({"deleted": filename})

@router.delete("/exports")
async def clear_exports(
    book_id: str,
    paths: StoragePaths = Depends(get_paths),
):
    """清除该书全部导出文件。返回被删除的文件列表。"""
    export_dir = paths.book_dir(book_id) / "exports"
    if not export_dir.exists():
        return ok({"deleted": [], "count": 0})
    deleted = [f.name for f in export_dir.iterdir() if f.is_file() and not f.name.endswith(".tmp")]
    for f in list(export_dir.iterdir()):
        if f.is_file() and not f.name.endswith(".tmp"):
            f.unlink(missing_ok=True)
    return ok({"deleted": deleted, "count": len(deleted)})
```

### 3.4 gating 更新

**修改文件**：`src/storyforge3/state/gating.py`

不需要改动——gating 按章节粒度控制，书籍删除是书籍粒度操作，不走章节 gating。

---

## 4. 验收标准

### 4.1 书籍归档

- [ ] `PATCH /books/{book_id}/status` 传入 `archived` 成功
- [ ] `GET /books` 默认不返回 archived 书
- [ ] `GET /books?include_archived=true` 返回含 archived 的书
- [ ] `GET /books/{book_id}` 对 archived 书仍可访问
- [ ] archived 书的所有章节 API 仍正常工作
- [ ] 后端测试覆盖 archived 过滤逻辑

### 4.2 书籍删除

- [ ] `GET /books/{book_id}/delete-preview` 返回文件列表和统计
- [ ] `DELETE /books/{book_id}` 备份到 `_trash/{book_id}_{timestamp}/`
- [ ] 删除后 `GET /books/{book_id}` 返回 404
- [ ] 删除后 `GET /books` 列表不含该书
- [ ] active 状态有未完成章节的书被拒绝删除（422 或类似错误码）
- [ ] exported/empty/completed 状态的书可以删除
- [ ] `_trash` 备份目录包含完整的书数据（book.json, chapters, truth, exports, state, plans）
- [ ] `POST /books/_trash/{backup_id}/restore` 从备份恢复书籍
- [ ] 恢复后 `GET /books/{book_id}` 返回正常数据
- [ ] 路径遍历防护：backup_id 不能包含 `..` 或 `/`
- [ ] 后端测试覆盖正常删除 + 拒绝删除 + 恢复

### 4.3 导出文件清理

- [ ] `DELETE /books/{book_id}/exports/{filename}` 删除指定文件
- [ ] 删除不存在的文件返回 404
- [ ] `DELETE /books/{book_id}/exports` 清除全部导出，返回文件列表
- [ ] 无导出文件时返回空列表（不报错）
- [ ] 路径遍历防护（同现有 download）
- [ ] 后端测试覆盖

### 4.4 质量基线

- [ ] 后端测试全量通过（≥603 passed）
- [ ] ruff clean
- [ ] 无交叉污染

---

## 5. 不在本指令范围

- ❌ 不做前端 UI（后端 API 先就位，前端后续跟进）
- ❌ 不做世界观/角色/卷纲删除（P1，涉及正文连续性和 truth 关联）
- ❌ 不做 run 记录清理（P1）
- ❌ 不做 reconcile heal 端点（P2）
- ❌ 不做 truth 版本记录（P2）
- ❌ 不做导出 hash 校验（P2）
- ❌ 不改 snapshot 恢复范围
- ❌ 不改 workspace restore 事务保护

---

## 6. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 误删活跃书 | 安全约束：active + 有未完成章节 → 拒绝删除 |
| rmtree 半失败（权限/锁文件） | 备份先于删除；捕获异常返回明确错误；保留 _trash 供手动恢复 |
| _trash 目录无限增长 | 备份目录带时间戳，后续可加自动清理（不在本指令） |
| 恢复时 book_id 冲突（同名新书已被创建） | restore 先检查目标是否已存在，已存在则报错提示用户先归档/删除 |
| truth.db 是跨书共享的 | 删除书时只清理该书条目，不影响其他书 truth |

---

## 7. 实现优先级建议

1. **先做书籍归档**（改动最小，只加枚举值 + 列表过滤）
2. **再做导出文件清理**（新增 2 个端点）
3. **最后做书籍删除+恢复**（需新建 BookDiscarder，参照 ChapterDiscarder 模式）
