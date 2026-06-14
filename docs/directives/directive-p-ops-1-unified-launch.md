# 指令 P-OPS-1：统一启动入口（消除"后端没起 → 页面坏 / 书消失"复发）

> 下发 Codex。前置：P1-1b 完成（545 passed）。
> 触发：2026-06-14 事故——后端 `:8000` 未运行导致"网页能开但报错 + 小说消失"，已是**第二次同因事故**（前次"页面打不开"同根因）。事故记录见 `docs/reviews/pm-consolidated-decisions-2026-06-14.md` §4。

## 背景

当前启动是**两条独立命令**：

```powershell
storyforge3 serve --port 8000     # 后端
cd web; pnpm dev                  # 前端 :5173，代理 /api → :8000
```

用户多次只起前端 → 后端死 → 所有 `/api/*` 失败 → "页面坏 / 书不见"。**这不是代码 bug，是没有单一启动入口的产品缺口。** 本指令补上。根因诊断（PM 已做）：前端 Vite 在 `:5173` 正常 serve，但 `:8000` 无监听 → 代理落空；数据层与代码均健康（`BOOK COUNT=1`，545 tests）。

## 任务

### 1. `storyforge3 dev` 子命令（新增）

一条命令同时管理后端 + 前端：

- **后端**：进程内起 FastAPI（复用 `serve` 的 `uvicorn.run(...)` 入口，端口默认 8000，`--port` 可覆盖，`--reload` 可选）
- **前端**：子进程起 `pnpm dev`（cwd = `web/`），stdout/stderr 转发到主日志，带前缀 `[api]` / `[web]`
- **健康门**：后端启动后轮询 `GET /api/health`，返回 ok 后才打印 `✓ ready → http://localhost:5173`；前端子进程先起，后端 ready 前主进程持续打印等待状态
- **统一退出**：Ctrl+C / SIGINT / SIGTERM → 优雅终止两个进程，端口释放，不留孤儿
- **清晰错误**：任一启动失败（端口占用 / venv 缺失 / `pnpm` 未装 / `web/` 不存在 / 前端端口被占）→ **一行人话错误 + 非零退出码**，不静默
- 不自动开浏览器（避免与 Tauri 冲突）；`--open` 可选才开

### 2. 启动诊断日志（补 P-IMP-1 D3，本轮一并做）

服务 ready 时打印摘要（让"导入成功但读不到 provider"这类问题一眼可见）：

```text
[sf3] providers.json = <绝对路径>  (exists=<bool>)
[sf3] active_provider = <label> (<model_id>)
[sf3] ccswitch_db   = <绝对路径>  (available=<bool>)
[sf3] books_dir     = <绝对路径>  (<N> books)
```

复用 P1-1b 已有的 `config.resolved_providers_config_dir()` / `resolved_ccswitch_db_path()` / `ProviderConfigManager.get_active()` / `BookService.list_books()`。

### 3. 文件改动

- `src/storyforge3/__main__.py`：加 `dev` 子命令分支
- 新增 `src/storyforge3/dev_runner.py`（或合入 `__main__`）：双进程生命周期 + 健康门 + 日志前缀 + 优雅退出
- `docs/quickstart.md`：顶部启动从"两条命令"改为 **`storyforge3 dev` 一条**；旧双命令降为"高级 / 排错"小节，并加**大字警示**：浏览器开发必须用 `dev`，否则后端不在线 → 书列表空
- `CLAUDE.md` Commands：加 `storyforge3 dev`

## Part 3：借鉴来源

| 借鉴 | 来源文件 | 方式 |
|------|---------|------|
| 双进程管理 + 健康门 + 优雅退出 + 清晰错误 | `src-tauri/src/process_manager.rs`（sidecar-first / venv-fallback + 30s health wait + 进程清理） | **模式复用** → Python `asyncio.subprocess` |
| uvicorn 进程内启动 | `src/storyforge3/__main__.py:104-108` 既有 `serve` | **直接复用** |
| Vite 子进程 | `web/` 既有 `pnpm dev` | **直接复用**（子进程化包装） |
| 健康检查轮询 | `web/src/tauriBootstrap.ts` `waitForApiReady` + `storyforge3 health` 既有逻辑 | **模式复用** |

**新写比例**：约 **50%**。双进程编排是新写；uvicorn / vite / health 各自既有。不引入新重依赖。

## 验收门禁

```powershell
.\.venv\Scripts\python.exe -m pytest --tb=short -q     # ≥545 不退步
.\.venv\Scripts\python.exe -m ruff check .               # clean
pnpm --dir web typecheck                                 # clean
```

手动：
- `storyforge3 dev` 一条命令 → 后端 + 前端都起 → 健康门打印 `✓ ready`
- Ctrl+C → 两进程退出，`:8000` / `:5173` 释放（`netstat` 验证）
- 模拟端口占用 / `web/` 缺失 → 一行人话错误 + 非零退出
- 启动日志含 providers.json 绝对路径 + active provider + books 数

## 必须覆盖的测试

- `dev_runner`：双进程启动 / 健康门通过 / 启动失败错误 / 优雅退出（mock 子进程 + 假 health 端点）
- 启动诊断日志：providers.json 路径 + active + db available + books 数 格式断言

## 红线

- ❌ 不改既有 `serve` 独立行为（`dev` 可复用其逻辑，但 `serve` 单独仍可用）
- ❌ 不引入新重依赖（stdlib `asyncio.subprocess` + 既有 uvicorn）
- ❌ 默认不自动开浏览器（除非 `--open`）
- ❌ 不动 `books/` 数据、不动 `.storyforge3/`、不动 ccswitch.db
- ❌ 不做热重载联动（uvicorn reload 与 vite HMR 各自独立即可）

## 回报

- commit hash（建议 `feat(dev): unified launch entry (backend+frontend) + startup diagnostics`）
- pytest + ruff + typecheck 结果
- 一次 `storyforge3 dev` 启动日志（含 providers.json 路径 + active provider + books 数）+ Ctrl+C 退出 netstat 证据

## Out of Scope

- ❌ 不改 Tauri 桌面端启动（已自带 sidecar/venv + health；本指令只补 dev / 浏览器路径）
- ❌ 不做生产打包入口（后续 follow-up）
- ❌ 不做 P-IMP-2/3/4（独立指令）
