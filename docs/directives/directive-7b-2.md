# Codex 指令：Phase 7B-2 — 快照管理 + 回滚

> 发出日期：2026-06-10
> 产品经理：Claude Code PM
> 执行者：Codex
> 前置条件：Phase 7B-1 完成（469 tests: 416 后端 + 53 前端, ruff clean）

---

## 任务概述

让作者能查看历史快照并在必要时回滚。当前快照系统在导出时自动创建 zip（最多 5 份），但前端看不到这些快照，也没有恢复能力。作者一旦误操作，无法自救。

**当前状态**：
- `SnapshotManager`（`snapshot.py`）有 `create_snapshot()` + `list_snapshots()`
- 快照格式：`{timestamp}_ch{chapter_no:04d}.zip` + `.meta.json`
- `list_snapshots()` 返回 `[{"book_id", "chapter_no", "timestamp", "file_count", "path"}]`
- 无 `restore_snapshot()` 方法
- 无 API 端点（无 `routes/snapshots.py`）
- 无 Protocol 定义
- 前端零代码

**核心原则**：
1. **回滚是危险操作**——必须二次确认，且只恢复章节正文和状态
2. **快照列表是只读展示**——列出元数据即可，不解压
3. **最小恢复范围**——只恢复 `chapters/` + `state/`，不动 truth 和 world（truth 应重新提取）
4. **借鉴现有模式**——`SnapshotManager` 的 zip 操作、`storage.py` 的原子写入

---

## Part 1：后端 — 快照 API + 恢复

### 1.1 `SnapshotManager.restore_snapshot()`

**文件**：`src/storyforge3/snapshot.py`

新增方法：

```python
def restore_snapshot(self, book_id: str, snapshot_path: str) -> dict:
    """从快照恢复章节正文和状态。返回恢复的文件列表。"""
    snap_dir = self._books_dir / book_id / "snapshots"
    zip_path = snap_dir / snapshot_path
    if not zip_path.exists():
        raise FileNotFoundError(f"snapshot not found: {snapshot_path}")

    book_dir = self._books_dir / book_id
    restored: list[str] = []

    with zipfile.ZipFile(zip_path, "r") as archive:
        for name in archive.namelist():
            # 只恢复 chapters/ 和 state/ 目录下的文件
            if name.startswith("chapters/") or name.startswith("state/"):
                target = book_dir / name
                target.parent.mkdir(parents=True, exist_ok=True)
                # 原子写入：先写 tmp 再 rename
                tmp = target.with_suffix(target.suffix + ".tmp")
                tmp.write_bytes(archive.read(name))
                tmp.replace(target)
                restored.append(name)

    return {"restored_files": restored, "count": len(restored)}
```

**安全约束**：
- 只恢复 `chapters/` 和 `state/` 前缀的文件——不动 truth、world、characters
- 使用 `archive.namelist()` 过滤，不信任 zip 内的路径（防止 zip slip 攻击）
- 检查 `name` 不包含 `..`（路径遍历防护）

**增强安全**：

```python
for name in archive.namelist():
    if ".." in name or name.startswith("/"):
        continue  # 跳过可疑路径
    if not (name.startswith("chapters/") or name.startswith("state/")):
        continue  # 只恢复白名单目录
    ...
```

### 1.2 API 端点

**新文件**：`src/storyforge3/api/routes/snapshots.py`

```python
from fastapi import APIRouter, Depends
from storyforge3.config import StoryForge3Config
from storyforge3.api.deps import get_config
from storyforge3.api.errors import not_found
from storyforge3.api.response import ok
from storyforge3.snapshot import SnapshotManager
from pydantic import BaseModel

router = APIRouter(prefix="/books/{book_id}/snapshots", tags=["snapshots"])


class SnapshotMeta(BaseModel):
    book_id: str
    chapter_no: int
    timestamp: str
    file_count: int
    path: str


class RestoreResult(BaseModel):
    restored_files: list[str]
    count: int


def _get_manager(config: StoryForge3Config = Depends(get_config)) -> SnapshotManager:
    return SnapshotManager(config.books_dir, max_count=config.snapshot_max_count)


@router.get("")
async def list_snapshots(
    book_id: str,
    manager: SnapshotManager = Depends(_get_manager),
):
    snapshots = manager.list_snapshots(book_id)
    return ok(snapshots)


@router.post("/{snapshot_path:path}/restore")
async def restore_snapshot(
    book_id: str,
    snapshot_path: str,
    manager: SnapshotManager = Depends(_get_manager),
):
    try:
        result = manager.restore_snapshot(book_id, snapshot_path)
    except FileNotFoundError as exc:
        raise not_found(str(exc)) from exc
    return ok(result)
```

**路由注册**：在 `app.py` 中注册 `router`，与其他路由并列。

**错误处理**：
- 快照不存在 → 404
- zip 损坏 → 500 internal error（让 FastAPI 默认处理）

### 1.3 Protocol

**不新增 Protocol**。快照操作是管理层面的功能，不走 Service 层。`SnapshotManager` 直接通过 API 路由的 Depends 注入使用。

---

## Part 2：前端 — 快照面板

### 2.1 API 层

**新文件**：`web/src/api/snapshots.ts`

```typescript
export interface SnapshotMeta {
  book_id: string;
  chapter_no: number;
  timestamp: string;
  file_count: number;
  path: string;
}

export interface RestoreResult {
  restored_files: string[];
  count: number;
}

export const snapshotsApi = {
  list: (bookId: string) => api.get<SnapshotMeta[]>(`/api/books/${bookId}/snapshots`),
  restore: (bookId: string, snapshotPath: string) =>
    api.post<RestoreResult>(`/api/books/${bookId}/snapshots/${encodeURIComponent(snapshotPath)}/restore`),
};
```

### 2.2 Hook

**文件**：`web/src/hooks/useSnapshots.ts`

**从 CC-Switch `useBackupManager.ts`（59 行）移植骨架**。去掉 rename/delete mutation，只保留 list + restore。

```typescript
// 移植自 cc-switch-main/src/hooks/useBackupManager.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { snapshotsApi } from "@/api/snapshots";

export function useSnapshotList(bookId: string) {
  return useQuery({
    queryKey: ["snapshots", bookId],
    queryFn: () => snapshotsApi.list(bookId),
    enabled: Boolean(bookId),
    retry: false,
  });
}

export function useSnapshotRestore(bookId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (snapshotPath: string) => snapshotsApi.restore(bookId, snapshotPath),
    onSuccess: async () => {
      // 移植自 useBackupManager 的 invalidateQueries 模式
      await queryClient.invalidateQueries({ queryKey: ["chapter-status"] });
      await queryClient.invalidateQueries({ queryKey: ["truth-history"] });
    },
  });
}
```

### 2.3 SnapshotPanel 组件

**新文件**：`web/src/components/snapshots/SnapshotPanel.tsx`

**从 CC-Switch `BackupListSection.tsx`（494 行）移植骨架**。具体移植映射：

| CC-Switch 代码 | SF3 适配 |
|---------------|---------|
| `useBackupManager()` → list/restore/remove/rename | 只用 `useSnapshotList()` + `useSnapshotRestore()` |
| `confirmFilename` state 控制确认对话框 | **直接复用**此模式 |
| `formatBackupDate()` 函数 | **直接复制** |
| `Dialog` + `DialogContent` + 确认/取消按钮 | **直接复用**组件结构 |
| `toast.success/error` 通知 | **直接复用**（同样用 sonner） |
| 重命名/删除行内编辑 | **去掉** |
| `isLoading` skeleton | **直接复用** |

**布局**：

```
┌───────────────────────────────────────────────────┐
│  📦 版本快照                      [刷新]          │
├───────────────────────────────────────────────────┤
│  2026-06-10T18:30:00Z   第 5 章   12 文件  [回滚] │
│  2026-06-10T12:15:00Z   第 3 章   11 文件  [回滚] │
│  ...                                              │
├───────────────────────────────────────────────────┤
│  无快照                                           │
│  快照在导出时自动创建（最多保留 5 份）。           │
└───────────────────────────────────────────────────┘
```

**回滚确认**：

点击"回滚"时弹出确认对话框（**移植自 `BackupListSection.tsx` 的 `confirmFilename` state + Dialog 模式**）：

```
⚠️ 确认回滚
将恢复"2026-06-10T18:30 第 5 章"快照中的章节正文和状态。
当前正文和状态将被覆盖。此操作不可撤销。

[取消]  [确认回滚]
```

**Props**：

```typescript
interface SnapshotPanelProps {
  bookId: string;
}
```

**时间格式化**：**直接复制** `BackupListSection.tsx:41-48` 的 `formatBackupDate()` 函数。将 ISO 时间戳转换为可读格式，例如 `2026-06-10 18:30`。

### 2.4 BookDetailPage 新增"快照"tab

**文件**：`web/src/pages/BookDetailPage.tsx`

在"真相"tab 之后新增"快照"tab：

```tsx
<TabsTrigger value="snapshots">快照</TabsTrigger>
```

```tsx
<TabsContent value="snapshots">
  <SnapshotPanel bookId={id} />
</TabsContent>
```

更新 `validTab`：加入 `"snapshots"`。

---

## Part 3：借鉴来源

### 主要借鉴：CC-Switch 备份管理系统

**这是本阶段最核心的借鉴来源**。CC-Switch 有一个完整的备份管理 UI，交互模式与快照管理完全对齐。

| 借鉴内容 | CC-Switch 来源文件 | 行数 | 借鉴方式 |
|---------|---------|------|---------|
| **备份列表 UI + 确认回滚对话框** | `cc-switch-main/src/components/settings/BackupListSection.tsx` | 494 行 | **直接移植**，去掉 i18n（本项目无 react-i18next），去掉重命名/删除（快照由系统管理），保留：列表渲染 + 确认回滚 Dialog + 安全备份提示 + toast 通知 |
| **备份管理 Hook** | `cc-switch-main/src/hooks/useBackupManager.ts` | 59 行 | **直接移植**，useQuery(list) + useMutation(restore) + invalidateQueries 模式。去掉 rename/delete mutation（快照无需这些操作） |
| **时间格式化** | `BackupListSection.tsx:41-48` `formatBackupDate()` | 8 行 | **直接复制** `formatBackupDate` 函数 |
| **文件大小格式化** | `BackupListSection.tsx:35-39` `formatBytes()` | 5 行 | **直接复制**（快照 zip 有文件大小时可用） |

### 次要借鉴：StoryForge3 内部

| 借鉴内容 | 来源文件 | 借鉴方式 |
|---------|---------|---------|
| zip 读取 | `snapshot.py:create_snapshot()` | 对称实现 restore（读取而非写入） |
| 原子写入 | `storage.py` / `workflow.py:_atomic_write_text()` | tmp + rename 模式 |
| meta.json 格式 | `snapshot.py:_write_meta()` | 复用现有格式，restore 不需要改 meta |
| API 路由模式 | `routes/truth.py` | 复用 Router + Depends + ok() 模式 |

### 移植适配清单

从 CC-Switch `BackupListSection.tsx` 移植时需要的改动：

| CC-Switch 原始 | StoryForge3 适配 |
|---------------|-----------------|
| `useBackupManager()` hook | 改为 `useSnapshotRestore()` hook（只保留 list + restore） |
| `backupsApi.listDbBackups()` | 改为 `snapshotsApi.list(bookId)` |
| `backupsApi.restoreDbBackup(filename)` | 改为 `snapshotsApi.restore(bookId, path)` |
| `useTranslation()` i18n | 去掉，直接硬编码中文文案 |
| `formatBytes()` 文件大小 | 快照 meta 无 size 字段，改为显示 `file_count` |
| 重命名/删除功能 | 去掉（快照由系统自动管理，用户不手动删） |
| DB 备份概念 | 改为"快照"概念（zip 包含 chapters+state+truth） |
| `backupRetainCount` 设置 | 去掉（已有 `snapshot_max_count` config） |

**新写比例**：约 **25%**（大幅降低）。前端 UI 从 CC-Switch 直接移植骨架（~60% 复用），后端 zip restore 与 create 对称（~30% 复用），真正新写的只有 API 路由和 zip 白名单过滤逻辑。

---

## 验收标准

### 后端

- [ ] `SnapshotManager.restore_snapshot()` 只恢复 `chapters/` + `state/`
- [ ] 路径遍历防护（跳过含 `..` 或绝对路径的 zip 条目）
- [ ] `GET /api/books/{book_id}/snapshots` 返回快照列表
- [ ] `POST /api/books/{book_id}/snapshots/{path}/restore` 执行回滚
- [ ] 快照不存在返回 404
- [ ] 路由注册到 `app.py`
- [ ] 现有 416 tests 不退步

### 前端

- [ ] `SnapshotPanel` 展示快照列表（时间+章节+文件数）
- [ ] 回滚按钮触发确认对话框
- [ ] 确认后调用 restore API
- [ ] 回滚成功后失效相关缓存
- [ ] 无快照时优雅降级
- [ ] `BookDetailPage` 新增"快照"tab

### 测试

- [ ] 后端：`SnapshotManager.restore_snapshot()` 测试（正常恢复、zip slip 防护、白名单过滤）
- [ ] 后端：`GET /snapshots` API 测试
- [ ] 后端：`POST /snapshots/{path}/restore` API 测试
- [ ] 前端：`SnapshotPanel` 渲染测试
- [ ] 前端：`snapshotsApi` 函数测试
- [ ] 469 基线 tests 不退步

### 质量

- [ ] `ruff check .` clean
- [ ] `pnpm build` clean（除已知 CodeMirror chunk 警告）
- [ ] `pnpm test` 全绿

---

## 估算工作量

| 部分 | 文件 | 预估行数 |
|------|------|---------|
| 后端 restore | `snapshot.py` | ~25 行 |
| 后端 API | `routes/snapshots.py` | ~40 行 |
| 后端路由注册 | `app.py` | ~2 行 |
| 后端测试 | `test_snapshots.py` | ~50 行 |
| 前端 API | `api/snapshots.ts` | ~15 行 |
| 前端 Hook | `hooks/useSnapshots.ts` | ~15 行（从 CC-Switch useBackupManager 移植） |
| 前端 SnapshotPanel | `SnapshotPanel.tsx` | ~60 行（从 CC-Switch BackupListSection 移植骨架） |
| 前端 BookDetailPage | `BookDetailPage.tsx` | ~6 行 |
| 前端测试 | `__tests__/` | ~35 行 |
| **合计** | **~9 个文件** | **~250 行** |

---

## 不做的事（Out of Scope）

- ❌ 不做恢复 truth / world / characters——truth 应重新提取，world/characters 手动管理
- ❌ 不做快照创建触发——已有导出前自动创建
- ❌ 不做快照删除——已有 max_count 自动清理
- ❌ 不做跨书快照——每本书独立管理
- ❌ 不做增量恢复——整本 chapters+state 一起恢复
- ❌ 不做恢复后自动重审计——作者可手动触发
