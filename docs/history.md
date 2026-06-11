# StoryForge3 阶段历史

> 更新时间：2026-06-12  
> 职责：记录已完成阶段。当前事实见 `docs/current.md`，后续计划见 `docs/next.md`。

## Phase 10A-2：后端 LLM 流式输出 + SSE 进度

状态：完成。

交付：

- `LLMService.generate_text_stream()` 支持 OpenAI Chat / Responses 流式解析，非流式格式降级到 `generate_text()`。
- `ChunkedGenerator` 新增 `on_progress` 回调，并在 chunk plan 超时或 provider 错误时按 outline 降级分段。
- 章节 draft/revise 路由发布 `pipeline:start`、`llm:progress`、`pipeline:complete/error`。
- `ChapterWorkflow` 在导出前确保当前章节 truth 已持久化，避免 dogfood 中 truth gap 被状态机 force 掩盖。

验证记录：核心相关测试 59 passed；覆盖率运行 498 passed / 91%。

## Phase 10A-1：覆盖率基线 + 文档治理

状态：完成。

交付：

- 新增 `docs/current.md`、`docs/history.md`、`docs/next.md`，删除旧的混合状态文档。
- 记录 pytest-cov 基线：总覆盖率 91%。
- 启用 ADR：FastAPI Service 分层、React/Vite 前端、Truth SQLite、Tauri sidecar、CC-Switch 只读集成。

## Phase 9：Prompt 质量修复

状态：完成。

交付：

- 升级 `chapter_service.py`、`character_service.py`、`volume_service.py` 的空壳 prompt。
- 加强 `compose-v1` 和 `audit-v1`。
- 为 prompt 内容和 schema 结构增加 9 个测试。

验证记录：486 后端测试通过，ruff clean。

## Phase 8.5：Dogfood RC

状态：完成。

交付：

- `README.md` 和 `docs/quickstart.md`：10 分钟启动 Web 工作台。
- `docs/dogfood-protocol.md`：真实写一章的测试协议。
- 冷启动 smoke：临时 venv 安装、CLI help、`storyforge3 serve`、`/api/health`、Vite 代理验证。
- `docs/release-setup.md` 更新 sidecar / venv fallback 描述。

遗留：真实写章 dogfood 需要继续积累样本。

## Phase 8A-1：Python Sidecar 打包

状态：完成。

交付：

- PyInstaller `--onedir` sidecar 入口、spec 和 Windows 构建脚本。
- Tauri 集成 `tauri-plugin-shell`、`externalBin`、`shell:allow-spawn`。
- Rust process manager 改为 sidecar-first / venv-fallback 双模式。

复盘：后续真实打包需对照 Manuskript / novelWriter 的 PyInstaller 经验，重点检查 datas、hidden imports、体积和杀毒误报。

## Phase 8B-1：Service 测试补齐

状态：完成。

交付：

- `PromptService` 7 个测试。
- `StyleService` 7 个测试。
- `TruthService` 6 个测试。
- Service 层 17/17 独立测试覆盖。

## Phase 7D：CI/CD + 用户数据管理

状态：完成。

交付：

- GitHub Actions：backend / frontend / desktop 三 job CI。
- Windows tag release 骨架和 Tauri updater artifact 配置。
- `WorkspaceService`：validate、backup、restore；恢复前自动安全备份。
- `/settings` 前端工作区设置页。

## Phase 7C：MCP 实战化

状态：完成。

交付：

- MCP tool 错误恢复建议。
- `next_step` 字段和结构化 `DraftResult`。
- 15 个 tool docstring 操作分层。
- `docs/mcp-registration.md` 注册指南。

## Phase 7B：质量运营面板

状态：完成。

交付：

- Truth 历史面板：6 类 truth 分组、章节切换、搜索过滤。
- Snapshot 管理和白名单回滚。
- Export preview：番茄、Markdown、起点格式预览、复制和下载。

## Phase 7A：写作工作台

状态：完成。

交付：

- 章节编辑保存：SHA-256 乐观锁、Ctrl+S、保存后 `NEEDS_REVIEW`。
- 审计定位：规则段落索引、snippet、CodeMirror 高亮。
- 修订 Diff：真实 revise、`.before.md` 快照、段落级左右对比。

## Phase 6：桌面端、短篇、同人、MCP

状态：完成。

交付：

- CodeMirror 编辑器。
- Tauri 桌面 scaffold 和 polish。
- 同人 Canon 导入和 4 维度审计。
- 短篇 5 步管线后端 + 前端。
- MCP Server 15 tool。

## Phase 5：前端 MVP + 基础设施

状态：完成。

交付：

- React/Vite/Tailwind/shadcn 前端 MVP。
- PipelineLogger JSONL 审计日志。
- Audit/Truth/Prompt/Style service 对齐。
- 导出前 zip 快照和自动清理。

## Phase 1-4：核心引擎

状态：完成。

交付：

- 从零建书、世界观、角色、卷纲、章节管线。
- 36 条机械审计、LLM 审计、修订模式。
- Truth 提取、SQLite 存储、上下文注入。
- FastAPI 路由、安全网、ContextBlock 跟踪、API 集成测试。
