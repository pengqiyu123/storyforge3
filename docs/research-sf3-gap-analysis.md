# 调研报告与 StoryForge3 现状对照分析

> 基于调研报告/目录下 8 份报告，对照 SF3 引擎实际实现状态。
> 日期：2026-06-07

## 对照总表

### 1. 桌面客户端框架选型

| 调研建议 | SF3 现状 | 状态 |
|----------|----------|------|
| Tauri 2 作为桌面客户端框架 | CLI + FastAPI serve，无桌面 GUI | ❌ 未实现 |
| 便携分发（portable zip ~8MB） | pip 安装 / `storyforge3 serve` HTTP API | ❌ 未实现 |
| React/Vue/Svelte 前端 + CodeMirror/TipTap 编辑器 | 无前端 | ❌ 未实现 |
| Rust 后端处理 AI API 调用 | Python asyncio + httpx | 🔧 不同技术栈 |
| 流式 AI 响应通过 channel 传递前端 | SSE `/api/events` 已实现 | ✅ 已实现 |

### 2. CC-Switch 统一配置与 Agent 调度

| 调研建议 | SF3 现状 | 状态 |
|----------|----------|------|
| CC-Switch 作为统一 provider 代理 | CC-Switch 只读 SQLite + provider import | ✅ 已实现 |
| 不存储真实 API key | `.storyforge3/providers.json` 存 key | 🔧 部分实现 |
| MCP Server 接口供外部 Agent 调用 | 无 MCP 接口 | ❌ 未实现 |
| CLI 接口 | 9 个 CLI 命令 | ✅ 已实现 |
| 桌面 IPC 通信 | 无桌面客户端 | ❌ 未实现 |

### 3. 开源 AI 小说写作工具架构

| 调研建议 | SF3 现状 | 状态 |
|----------|----------|------|
| 单用户本地客户端 + 外部 AI API | CLI 引擎 + 外部 AI API | ✅ 已实现 |
| Markdown/JSON 文件存储 + SQLite 索引 | Markdown/JSON 内容文件 + SQLite truth | ✅ 已实现 |
| 多 provider 网关 + 流式支持 | LLMService 多协议 fallback | ✅ 已实现 |
| Truth Files 结构化设定 | SQLite truth_entries + JSON 备份 | ✅ 已实现 |
| Preview-before-apply | ChapterResult preview + human_confirm 门 | ✅ 已实现 |
| ContextPackage 可审计上下文包 | 上下文拼装在代码中，无 source tracking | 🔧 部分实现 |

### 4. 横向对比与融合架构

| 调研建议 | SF3 现状 | 状态 |
|----------|----------|------|
| InkOS 式创作管线 | plan→draft→normalize→audit→revise→truth→export | ✅ 已实现 |
| novelWriter 式本地项目文件夹 | books/{book_id}/ 结构化目录 | ✅ 已实现 |
| 51mazi 式中文上下文组装 | world + characters + truth + context 拼装 | ✅ 已实现 |
| NovelForge 式 preview/apply | human_confirm 门控 | ✅ 已实现 |
| 灵感对话（InspirationChat） | 无 | ❌ 未实现 |
| RAG 检索增强生成 | truth_retriever.retrieve_for_prompt 基础检索 | 🔧 部分实现 |

### 5. 本地客户端 AI API 调用架构

| 调研建议 | SF3 现状 | 状态 |
|----------|----------|------|
| 后端处理 API key / HTTP / 流式 / 重试 | LLMService 完整实现 | ✅ 已实现 |
| 前端不直接调用 SDK | 无前端，API 层在后端 | ✅ 已实现 |
| ContextAssembler 生成 ContextPackage | 各 step 内组装，无统一 assembler | 🔧 部分实现 |
| SessionStore 维护对话状态 | 无对话状态管理 | ❌ 未实现 |
| 流式部分保存（partial salvage） | 无流式部分保存 | ❌ 未实现 |

### 6. 混合存储方案

| 调研建议 | SF3 现状 | 状态 |
|----------|----------|------|
| 文件 = 真实来源，SQLite = 索引/缓存 | Markdown/JSON 内容 + SQLite truth | ✅ 已实现 |
| JSONL 审计日志 | 无 JSONL 日志 | ❌ 未实现 |
| 原子写入（temp file + rename） | storage.write_text 直接写入 | 🔧 部分实现 |
| 历史快照（覆盖前保存） | 无快照机制 | ❌ 未实现 |
| 项目级 Zip 备份 | 无 | ❌ 未实现 |
| 可重建索引（从源文件恢复） | truth 可重建，其他索引不依赖 SQLite | ✅ 已实现 |

### 7. 源码级架构改造

| 调研建议 | SF3 现状 | 状态 |
|----------|----------|------|
| Truth Files 双格式（JSON + Markdown） | SQLite + JSON 备份，无 Markdown 投影 | 🔧 部分实现 |
| Context 预算分配（P0-P3） | 无预算管理，max_chars 硬编码 | 🔧 部分实现 |
| Hook debt（悬空伏笔追踪） | 无 | ❌ 未实现 |
| 四道人工确认门 | human_confirm 一道门控 | 🔧 部分实现 |
| 段落级编辑指令 | patch revise 实现了 find/replace 局部修改 | ✅ 已实现 |

### 8. 灵感对话到端到端工作流

| 调研建议 | SF3 现状 | 状态 |
|----------|----------|------|
| 自然语言意图解析 | 无 | ❌ 未实现 |
| 上下文来源追踪 | 无 source tracking | ❌ 未实现 |
| 流式输出到草稿面板 | SSE 事件推送 | ✅ 已实现 |
| Diff 预览所有变更 | 无 diff 功能 | ❌ 未实现 |
| 所有操作记入 JSONL + SQLite | LLMCallRecord 记录在内存 | 🔧 部分实现 |

## 汇总

### ✅ 已实现（SF3 核心能力）

- 创作管线：plan → draft(chunked) → normalize → audit → revise(patch) → truth → export
- 多协议 AI 网关：OpenAI Chat/Responses + Anthropic + Gemini，自动 fallback
- CC-Switch 集成：只读 SQLite provider，import 到本地配置
- Truth 系统：SQLite truth_entries + JSON 备份 + 跨章检索
- 质量闭环：36 条机械审计 + 5 种 revision mode + patch revise
- FastAPI REST API + SSE 事件推送
- CLI 工具（9 个命令）
- Prompt Registry 版本管理
- ChunkedGenerator 长文分块生成
- Patch Revise 局部修订

### 🔧 部分实现（需深化）

- ContextPackage：有上下文拼装，缺 source tracking 和可审计性
- Context 预算：有 max_chars 限制，缺优先级分配和 capContextBlock
- API key 管理：provider.json 存 key，应改为 CC-Switch 代理
- 原子写入：直接写入，无 temp+rename 保护
- Diff 预览：有 ChapterResult preview，无文本 diff

### ❌ 未实现（桌面客户端专属 / 新功能）

- **Tauri 2 桌面客户端**（前端 + 便携分发）
- **MCP Server 接口**
- **灵感对话（InspirationChat）**
- **自然语言意图解析**
- **JSONL 审计日志**
- **历史快照 / Zip 备份**
- **流式部分保存（partial salvage）**
- **Hook debt 悬空伏笔追踪**
- **SessionStore 对话状态**
- **Truth Files Markdown 投影**

## 引擎深化优先级建议

以下项目可在 SF3 引擎内推进，不依赖桌面客户端：

| 优先级 | 项目 | 依据 |
|--------|------|------|
| ✅ | 3 章多章 E2E 稳定通过 | 已达成：`books/e2e-multi-20260608-180847`，`3/3 exported` |
| P0 | 失败时持久化中间产物（audit snapshot / patch） | 可观测性，支持 post-mortem |
| P1 | C' 协议族过滤 | 防御性清理，减少无效 fallback |
| P1 | Context source tracking | 为未来 ContextPackage 打基础 |
| P1 | 原子写入（temp + rename） | 数据安全 |
| P2 | JSONL 操作日志 | 可审计性 |
| P2 | Context 预算分配（P0-P3） | 长篇上下文管理 |
| P2 | MCP Server 接口 | 外部 Agent 集成 |
