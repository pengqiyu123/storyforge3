# 调研报告与 StoryForge3 现状对照分析

> 基于调研报告/目录下 8 份报告，对照 SF3 引擎实际实现状态。
> 原始日期：2026-06-07
> 最后更新：2026-06-10（Phase 7B-1 完成后全面校正）

## 对照总表

### 1. 桌面客户端框架选型

| 调研建议 | SF3 现状（2026-06-10） | 状态 |
|----------|----------------------|------|
| Tauri 2 作为桌面客户端框架 | Phase 6D-1/6D-2 完成：Tauri 2 桌面壳 + Python 进程管理 + 托盘 + 窗口 | ✅ 已实现 |
| 便携分发（portable zip ~8MB） | cargo tauri build 可产出安装包，CI/CD 待 7D | 🔧 部分实现 |
| React/Vue/Svelte 前端 + CodeMirror/TipTap 编辑器 | Phase 5A 前端 MVP + Phase 6A-1 CodeMirror 编辑器（从 CC-Switch 移植） | ✅ 已实现 |
| Rust 后端处理 AI API 调用 | Python asyncio + httpx（刻意选择，Rust 只做桌面壳） | 🔧 不同技术栈（设计决策） |
| 流式 AI 响应通过 channel 传递前端 | SSE `/api/events` 已实现 | ✅ 已实现 |

### 2. CC-Switch 统一配置与 Agent 调度

| 调研建议 | SF3 现状（2026-06-10） | 状态 |
|----------|----------------------|------|
| CC-Switch 作为统一 provider 代理 | CC-Switch 只读 SQLite + provider import（双层路由） | ✅ 已实现 |
| 不存储真实 API key | `.storyforge3/providers.json` 存 key（本地桌面应用，可接受） | 🔧 部分实现 |
| MCP Server 接口供外部 Agent 调用 | Phase 6E-1/6E-2 完成：FastMCP + 15 tool + STDIO transport | ✅ 已实现 |
| CLI 接口 | 9 个 CLI 命令 + `storyforge3 mcp` MCP 入口 | ✅ 已实现 |
| 桌面 IPC 通信 | Tauri 桌面壳通过 HTTP/SSE 与 FastAPI 通信（不依赖 Tauri IPC） | ✅ 已实现（设计决策） |

### 3. 开源 AI 小说写作工具架构

| 调研建议 | SF3 现状（2026-06-10） | 状态 |
|----------|----------------------|------|
| 单用户本地客户端 + 外部 AI API | CLI + Web + Tauri 桌面，全部通过 FastAPI | ✅ 已实现 |
| Markdown/JSON 文件存储 + SQLite 索引 | Markdown/JSON 内容文件 + SQLite truth | ✅ 已实现 |
| 多 provider 网关 + 流式支持 | LLMService 多协议 fallback（4 种 API 格式） | ✅ 已实现 |
| Truth Files 结构化设定 | SQLite truth_entries + JSON 备份 + 前端 TruthPanel 可视化 | ✅ 已实现 |
| Preview-before-apply | ChapterResult preview + human_confirm 门 | ✅ 已实现 |
| ContextPackage 可审计上下文包 | Phase 4 完成：ContextBlock/ContextPackage + Priority 枚举 + source tracking | ✅ 已实现 |

### 4. 横向对比与融合架构

| 调研建议 | SF3 现状（2026-06-10） | 状态 |
|----------|----------------------|------|
| InkOS 式创作管线 | plan→draft→normalize→audit→revise→truth→export（完整闭环） | ✅ 已实现 |
| novelWriter 式本地项目文件夹 | books/{book_id}/ 结构化目录 | ✅ 已实现 |
| 51mazi 式中文上下文组装 | world + characters + truth + context 拼装 | ✅ 已实现 |
| NovelForge 式 preview/apply | human_confirm 门控 | ✅ 已实现 |
| 灵感对话（InspirationChat） | 无 | ❌ 未实现 |
| RAG 检索增强生成 | truth_retriever.retrieve_for_prompt + SQLite 向量检索 | ✅ 已实现 |
| 同人模式（fanfic） | Phase 6C 完成：4 模式 + canon 导入 + 4 维度审计 | ✅ 已实现 |
| 短篇管线 | Phase 6B-1/6B-2 完成：5 步管线 + 前端 + 一键运行 | ✅ 已实现 |

### 5. 本地客户端 AI API 调用架构

| 调研建议 | SF3 现状（2026-06-10） | 状态 |
|----------|----------------------|------|
| 后端处理 API key / HTTP / 流式 / 重试 | LLMService 完整实现（2s/4s/8s backoff + 5 attempts） | ✅ 已实现 |
| 前端不直接调用 SDK | 前端通过 api/ 层 + React Query 调用 FastAPI | ✅ 已实现 |
| ContextAssembler 生成 ContextPackage | Phase 4 完成：_draft_context_package() + 优先级裁剪 | ✅ 已实现 |
| SessionStore 维护对话状态 | 无对话状态管理 | ❌ 未实现 |
| 流式部分保存（partial salvage） | 无流式部分保存（长文用 ChunkedGenerator 分段） | 🔧 替代方案 |

### 6. 混合存储方案

| 调研建议 | SF3 现状（2026-06-10） | 状态 |
|----------|----------------------|------|
| 文件 = 真实来源，SQLite = 索引/缓存 | Markdown/JSON 内容 + SQLite truth | ✅ 已实现 |
| JSONL 审计日志 | Phase 5C-1 完成：PipelineLogger + 7 步管线钩子 | ✅ 已实现 |
| 原子写入（temp file + rename） | Phase 4A-1 完成：storage._atomic_write_text() temp+rename | ✅ 已实现 |
| 历史快照（覆盖前保存） | Phase 5C-3 完成：导出前自动 zip 快照 + meta.json + 自动清理 | ✅ 已实现 |
| 项目级 Zip 备份 | 同上（snapshot.py SnapshotManager） | ✅ 已实现 |
| 可重建索引（从源文件恢复） | truth 可重建，其他索引不依赖 SQLite | ✅ 已实现 |

### 7. 源码级架构改造

| 调研建议 | SF3 现状（2026-06-10） | 状态 |
|----------|----------------------|------|
| Truth Files 双格式（JSON + Markdown） | SQLite + JSON 备份 + 前端 TruthPanel 可视化（无需 Markdown 投影） | ✅ 已实现（替代方案） |
| Context 预算分配（P0-P3） | Phase 4 完成：ContextPriority 枚举（CRITICAL/HIGH/MEDIUM/LOW） + budget trimming | ✅ 已实现 |
| Hook debt（悬空伏笔追踪） | 无 | ❌ 未实现 |
| 四道人工确认门 | human_confirm 一道门控 + 前端 AuditResultPanel + RevisionDiffPanel + 手动编辑 | ✅ 已实现（替代方案） |
| 段落级编辑指令 | patch revise find/replace + before.md 快照 + 段落级 diff | ✅ 已实现 |

### 8. 灵感对话到端到端工作流

| 调研建议 | SF3 现状（2026-06-10） | 状态 |
|----------|----------------------|------|
| 自然语言意图解析 | 无 | ❌ 未实现 |
| 上下文来源追踪 | Phase 4 完成：ContextBlock.context_sources 字段 | ✅ 已实现 |
| 流式输出到草稿面板 | SSE 事件推送 + 前端实时状态更新 | ✅ 已实现 |
| Diff 预览所有变更 | Phase 7A-3 完成：段落级 diff + RevisionDiffPanel 左右对比 | ✅ 已实现 |
| 所有操作记入 JSONL + SQLite | Phase 5C-1 JSONL 日志 + LLMCallRecord 内存记录 | ✅ 已实现 |
| 审计问题定位 | Phase 7A-2 完成：paragraph_indices + snippet + CodeMirror 高亮 + 滚动定位 | ✅ 已实现 |
| 章节手动编辑 | Phase 7A-1 完成：SHA-256 乐观锁 + PUT /text + 脏状态 + Ctrl+S | ✅ 已实现 |

## 汇总

### ✅ 已实现（截至 Phase 7B-1）

**核心引擎（Phase 1-4）**：
- 创作管线：plan → draft(chunked) → normalize → audit → revise(patch) → truth → export
- 多协议 AI 网关：OpenAI Chat/Responses + Anthropic + Gemini，自动 fallback
- CC-Switch 集成：只读 SQLite provider，双层路由
- Truth 系统：SQLite truth_entries + JSON 备份 + 跨章检索
- 质量闭环：36 条机械审计 + 5 种 revision mode + patch revise
- 原子写入 + 失败诊断 + Context 追踪 + 优先级预算

**API + CLI（Phase 1）**：
- FastAPI REST API（37+ 端点，13 路由模块）+ SSE 事件推送
- CLI 工具（9 个命令）+ Prompt Registry 版本管理

**前端 MVP（Phase 5A）**：
- React 19 + Vite 7 + TypeScript + Tailwind 4 + shadcn/ui
- Book CRUD + Chapter Pipeline + Dashboard + SSE + FocusMode

**基础设施（Phase 5C）**：
- PipelineLogger JSONL 审计日志（7 步管线钩子）
- 11/11 Service Protocol 实现 + 导出前 zip 快照

**扩展功能（Phase 6）**：
- CodeMirror 编辑器（CC-Switch 移植）
- Tauri 2 桌面壳（进程管理 + 托盘 + 窗口 + 自动更新）
- 同人模式（canon 导入 + 4 维度审计）
- 短篇管线（5 步 + 前端 + 一键运行）
- MCP Server（15 tool + STDIO）

**写作工作台（Phase 7A）**：
- 章节手动编辑 + SHA-256 乐观锁 + Ctrl+S
- 审计问题段落定位 + CodeMirror 高亮
- 真实修订执行 + 段落级 diff + RevisionDiffPanel

**质量运营（Phase 7B-1）**：
- Truth 可视化面板（6 类分组 + 章节切换 + 搜索过滤）

### ❌ 未实现（截至 Phase 7B-1）

| 功能 | 优先级 | 说明 | 归属阶段 |
|------|--------|------|---------|
| **Hook debt 悬空伏笔追踪** | 中 | 跨章钩子状态管理，对长篇连载有价值 | 远期 |
| **灵感对话（InspirationChat）** | 低 | 创意辅助功能，非核心管线 | 远期 |
| **自然语言意图解析** | 低 | MCP 已提供结构化 tool 接口 | 远期 |
| **SessionStore 对话状态** | 低 | 当前管线无状态，不需要 | 远期 |
| **流式部分保存** | 低 | ChunkedGenerator 分段生成已缓解 | 远期 |
| **通知渠道（Telegram/飞书/企微）** | 中 | Phase 5B 已跳过，Daemon 用户需盯终端 | 可选穿插 |
| **CI/CD + 签名 + 发布** | 高 | Phase 7D 计划中 | 7D |
| **Python 打包嵌入 Tauri** | 中 | 发布阶段需求 | 远期 |

### 引擎深化优先级（原表更新）

| 优先级 | 项目 | 状态 |
|--------|------|------|
| ✅ | 3 章多章 E2E 稳定通过 | 已达成：3/3 exported |
| ✅ | 失败时持久化中间产物 | Phase 4 完成：_persist_diagnostics |
| ✅ | Context source tracking | Phase 4 完成：ContextBlock + Priority |
| ✅ | 原子写入 | Phase 4A-1 完成 |
| ✅ | JSONL 操作日志 | Phase 5C-1 完成 |
| ✅ | Context 预算分配 | Phase 4 完成：ContextPriority 枚举 |
| ✅ | MCP Server 接口 | Phase 6E 完成：15 tool |
| ✅ | Diff 预览 | Phase 7A-3 完成 |
| ✅ | 审计问题定位 | Phase 7A-2 完成 |
| ✅ | 章节手动编辑 | Phase 7A-1 完成 |
| ✅ | Truth 可视化 | Phase 7B-1 完成 |
| ⬜ | 快照管理 + 回滚 | Phase 7B-2 指令已发出 |
| ⬜ | 导出预览 | Phase 7B-3 计划中 |
| ⬜ | CI/CD + 签名 | Phase 7D 计划中 |

## 测试基线（Phase 7B-1）

| 层 | 测试数 |
|----|--------|
| Python 后端 | 416 tests |
| React 前端 | 53 tests |
| Rust 桌面壳 | 4 tests（既有基线） |
| **合计** | **473 tests** |
