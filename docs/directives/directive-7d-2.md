# Codex 指令：Phase 7D-2 — 用户数据管理

> 发出日期：2026-06-10
> 产品经理：Claude Code PM
> 执行者：Codex
> 前置条件：Phase 7D-1 完成（CI/CD 就绪，436+ tests, ruff clean）

---

## 任务概述

为 StoryForge3 添加工作区管理能力：验证目录结构完整性、一键备份/恢复、首次启动引导。让用户的数据不再依赖手动管理。

**当前状态**：
- `StoragePaths`（`storage.py`）定义了完整路径结构但无验证逻辑
- `BookStorage.list_book_ids()` 扫描 `books_root` 下含 `book.json` 的目录
- `ExportService` 写入快照（5 份，zip 格式，含 meta.json）但无用户级备份
- `config.py` 有 `books_dir: str = "books"` 配置，无工作区初始化检查
- 前端 14 个路由模块已有，无 workspace 相关 API
- 14 个前端 API 模块已有，无 workspace 模块

**核心决策**：
1. **纯后端 + 前端实现** — 不改 Tauri Rust 代码，首次引导通过 web UI 而非原生对话框
2. **备份 = zip 整个 books 目录** — 包含所有书籍、章节、状态、配置
3. **恢复前创建安全备份** — 恢复操作不可逆，必须先备份当前数据
4. **验证 = 检查目录结构** — 不是内容审计，仅确认文件/目录存在且可读写

---

## Part 1：后端 — WorkspaceService + API

### 1.1 数据模型

**文件**：`src/storyforge3/models.py`（追加）

```python
@dataclass(frozen=True)
class WorkspaceValidation:
    valid: bool
    books_dir: str
    book_count: int
    issues: tuple[str, ...]

@dataclass(frozen=True)
class BackupResult:
    path: str
    book_count: int
    size_bytes: int
    created_at: str  # ISO 8601

@dataclass(frozen=True)
class RestoreResult:
    success: bool
    book_count: int
    backup_path: str  # 安全备份路径
    message: str
```

### 1.2 WorkspaceService

**新文件**：`src/storyforge3/services/workspace_service.py`

```python
class WorkspaceService:
    def __init__(self, config: StoryForge3Config):
        self._config = config
        self._books_dir = Path(config.books_dir)

    def validate(self) -> WorkspaceValidation:
        """验证工作区目录结构。"""
        issues = []
        if not self._books_dir.exists():
            issues.append(f"工作区目录不存在: {self._books_dir}")
        elif not self._books_dir.is_dir():
            issues.append(f"工作区路径不是目录: {self._books_dir}")
        else:
            # 检查可写
            test_file = self._books_dir / ".sf3_write_test"
            try:
                test_file.write_text("ok")
                test_file.unlink()
            except OSError as e:
                issues.append(f"工作区目录不可写: {e}")
        book_count = len(list(self._books_dir.glob("*/book.json"))) if self._books_dir.exists() else 0
        return WorkspaceValidation(
            valid=len(issues) == 0,
            books_dir=str(self._books_dir),
            book_count=book_count,
            issues=tuple(issues),
        )

    def backup(self) -> BackupResult:
        """创建工作区 zip 备份。"""
        self._ensure_valid()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_path = self._books_dir.parent / f"sf3-backup-{timestamp}.zip"
        book_count = 0
        size_bytes = 0
        with ZipFile(zip_path, "w", ZIP_DEFLATED) as zf:
            for file_path in sorted(self._books_dir.rglob("*")):
                if file_path.is_file() and not file_path.name.startswith("."):
                    arcname = file_path.relative_to(self._books_dir)
                    zf.write(file_path, arcname)
                    if file_path.name == "book.json":
                        book_count += 1
        size_bytes = zip_path.stat().st_size
        return BackupResult(
            path=str(zip_path),
            book_count=book_count,
            size_bytes=size_bytes,
            created_at=datetime.now().isoformat(),
        )

    def restore(self, zip_path: Path) -> RestoreResult:
        """从 zip 恢复工作区。恢复前自动创建安全备份。"""
        # 1. 验证 zip 内容
        with ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            if not any("book.json" in n for n in names):
                return RestoreResult(success=False, book_count=0, backup_path="", message="无效的备份文件：未找到 book.json")

        # 2. 创建安全备份
        safety_backup = self.backup()

        # 3. 清空并恢复
        if self._books_dir.exists():
            shutil.rmtree(self._books_dir)
        self._books_dir.mkdir(parents=True, exist_ok=True)

        with ZipFile(zip_path, "r") as zf:
            zf.extractall(self._books_dir)

        book_count = len(list(self._books_dir.glob("*/book.json")))
        return RestoreResult(
            success=True,
            book_count=book_count,
            backup_path=safety_backup.path,
            message=f"恢复成功，共 {book_count} 本书。安全备份: {safety_backup.path}",
        )

    def _ensure_valid(self) -> None:
        result = self.validate()
        if not result.valid:
            raise ValueError("；".join(result.issues))
```

### 1.3 API 路由

**新文件**：`src/storyforge3/api/routes/workspace.py`

```python
from fastapi import APIRouter, UploadFile, File
from storyforge3.services.workspace_service import WorkspaceService
# ... imports

router = APIRouter(prefix="/workspace", tags=["workspace"])

def _service() -> WorkspaceService:
    # 复用 app.py 的依赖注入模式
    ...

@router.get("/validate")
async def validate_workspace():
    """验证工作区目录结构。"""
    return _service().validate()

@router.post("/backup")
async def backup_workspace():
    """创建工作区 zip 备份并返回下载。"""
    result = _service().backup()
    return FileResponse(result.path, media_type="application/zip", filename=Path(result.path).name)

@router.post("/restore")
async def restore_workspace(file: UploadFile = File(...)):
    """从 zip 恢复工作区。"""
    # 保存上传到临时文件
    tmp = Path(f".restore_upload_{file.filename}")
    with open(tmp, "wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        result = _service().restore(tmp)
        return result
    finally:
        tmp.unlink(missing_ok=True)
```

**修改文件**：`src/storyforge3/api/app.py` — 注册新路由

```python
from storyforge3.api.routes.workspace import router as workspace_router
# ...
app.include_router(workspace_router, prefix="/api")
```

### 1.4 Protocol 注册

在 `src/storyforge3/services/protocols.py` 中不需要添加 Protocol（WorkspaceService 不通过 Protocol 注入，它直接从 config 构造，与 ExportService 的快照管理类似）。

---

## Part 2：前端 — Workspace API + UI

### 2.1 API 模块

**新文件**：`web/src/api/workspace.ts`

```typescript
import { api } from "./client";

export interface WorkspaceValidation {
  valid: boolean;
  books_dir: string;
  book_count: number;
  issues: string[];
}

export interface RestoreResult {
  success: boolean;
  book_count: number;
  backup_path: string;
  message: string;
}

export const workspaceApi = {
  validate: () => api.get<WorkspaceValidation>("/workspace/validate"),

  backup: async () => {
    const resp = await fetch("/api/workspace/backup", { method: "POST" });
    if (!resp.ok) throw new Error("Backup failed");
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = resp.headers.get("content-disposition")?.match(/filename="(.+)"/)?.[1] ?? "sf3-backup.zip";
    a.click();
    URL.revokeObjectURL(url);
  },

  restore: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    const resp = await fetch("/api/workspace/restore", { method: "POST", body: form });
    return resp.json() as Promise<RestoreResult>;
  },
};
```

### 2.2 WorkspaceSettings 组件

**新文件**：`web/src/components/WorkspaceSettings.tsx`

组件结构：
- 显示当前工作区路径（`validations.books_dir`）
- 显示书籍数量（`validations.book_count`）
- 验证状态指示器（绿色 ✓ / 红色 ✗ + issues 列表）
- "验证"按钮 → 调用 `workspaceApi.validate()`
- "备份"按钮 → 调用 `workspaceApi.backup()` → 触发浏览器下载
- "恢复"按钮 → 文件选择 → 确认对话框 → 调用 `workspaceApi.restore()` → 显示结果

使用现有 shadcn 组件：`Card`, `Button`, `Alert`, `Dialog`。

### 2.3 Settings 页面

在现有路由中添加 `/settings` 路由，或在 `BookDetailPage` 的现有 tab 系统中添加"设置"tab。

**推荐**：在 `App.tsx` 路由中添加 `/settings` 路由，侧边栏底部添加"设置"链接。WorkspaceSettings 是该页面的内容。

---

## Part 3：借鉴来源

| 借鉴内容 | 来源文件 | 行数 | 借鉴方式 |
|---------|---------|------|---------|
| **目录验证模式** | SF2 `engine/storage/json_state_store.py:51-82` `ensure_book_state_initialized()` | ~30 行 | **模式复用**：目录存在性检查 + 必要文件检测，但 SF3 更轻量（仅检查顶层结构） |
| **zip 备份/恢复** | CC-Switch `src-tauri/src/database/backup.rs` `backup_database_file()` + `restore_from_backup()` | ~60 行 | **模式复用**：安全备份 → 清空 → 恢复的三步模式，移植为 Python zipfile |
| **恢复前安全备份** | CC-Switch `backup.rs` 安全备份逻辑 | ~10 行 | **直接复用**：任何恢复操作前自动创建当前状态备份 |
| **前端文件上传下载** | SF3 `web/src/api/exports.ts` `getExportFile()` | ~15 行 | **直接复用**：blob 下载模式 |
| **状态验证 UI** | SF3 `web/src/components/` 中 HealthStatus 等 | ~20 行 | **模式复用**：状态指示器 + 问题列表 |

**新写比例**：约 **50%**。WorkspaceService 的备份/恢复核心逻辑是新写的，但模式来自 CC-Switch 和 SF2。API 路由和前端组件遵循现有约定。

### 移植适配清单

| 源项目原始 | SF3 适配 |
|-----------|---------|
| CC-Switch Rust `backup_database_file()` 备份 SQLite 文件 | SF3 Python `zipfile.ZipFile` 备份整个 books 目录 |
| CC-Switch `restore_from_backup()` 直接覆盖 SQLite | SF3 `shutil.rmtree()` + `zf.extractall()` 先清空再恢复 |
| CC-Switch 备份命名 `db_backup_YYYYMMDD_HHMMSS.db` | SF3 备份命名 `sf3-backup-YYYYMMDD_HHMMSS.zip` |
| SF2 `ensure_book_state_initialized()` 创建全部 JSON 文件 | SF3 `validate()` 只检查不创建（创建由 BookService 负责） |

---

## 验收标准

### 后端

- [ ] `WorkspaceService.validate()` 检查目录存在性、类型、可写性
- [ ] `WorkspaceService.backup()` 创建 zip，包含所有书籍数据
- [ ] `WorkspaceService.restore()` 验证 zip、创建安全备份、恢复数据
- [ ] 恢复无效 zip（无 book.json）返回 `success=False` 且不修改文件系统
- [ ] `GET /api/workspace/validate` 返回 `WorkspaceValidation`
- [ ] `POST /api/workspace/backup` 返回 zip 文件下载
- [ ] `POST /api/workspace/restore` 接受 multipart 上传，返回 `RestoreResult`
- [ ] `app.py` 注册 workspace_router

### 前端

- [ ] `workspace.ts` API 模块存在，包含 validate/backup/restore 三个方法
- [ ] `WorkspaceSettings` 组件显示工作区路径、书籍数、验证状态
- [ ] 备份按钮触发 zip 下载
- [ ] 恢复按钮有文件选择和确认对话框

### 测试

- [ ] `test_workspace_service.py`：validate（valid/missing/not-dir/not-writable）、backup（creates zip, includes books）、restore（valid zip, invalid zip, safety backup created）
- [ ] API 测试：validate endpoint, backup endpoint returns zip, restore endpoint handles upload
- [ ] 现有 436 tests 不退步

### 质量

- [ ] `ruff check .` clean
- [ ] `pnpm --dir web build` clean

---

## 估算工作量

| 部分 | 文件 | 预估行数 |
|------|------|---------|
| 数据模型 | `models.py`（追加） | ~15 行新增 |
| WorkspaceService | `services/workspace_service.py` | ~80 行新增 |
| API 路由 | `api/routes/workspace.py` | ~40 行新增 |
| app.py 注册 | `api/app.py` | ~2 行改动 |
| 后端测试 | `tests/test_workspace_service.py` | ~80 行新增 |
| 前端 API | `web/src/api/workspace.ts` | ~30 行新增 |
| 前端组件 | `web/src/components/WorkspaceSettings.tsx` | ~80 行新增 |
| 路由/侧边栏 | `web/src/App.tsx` 或相关 | ~10 行改动 |
| 前端测试 | `web/src/__tests__/` | ~20 行新增 |
| **合计** | **9 个文件** | **~360 行** |

---

## 不做的事（Out of Scope）

- ❌ 不改 Tauri Rust 代码（首次引导通过 web UI 而非原生对话框）
- ❌ 不做自动定期备份（仅手动触发）
- ❌ 不做远程备份（仅本地 zip）
- ❌ 不做工作区迁移（从旧路径移到新路径）
- ❌ 不做数据修复（validate 只报告，不自动修复）
- ❌ 不改现有 Service / Protocol 接口
- ❌ 不引入新依赖
