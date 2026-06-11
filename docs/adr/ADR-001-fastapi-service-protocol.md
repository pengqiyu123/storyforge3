# ADR-001: FastAPI + Service Protocol 分层

## Status

Accepted

## Context

StoryForge3 需要同时服务 CLI、Web、Tauri 桌面端和 MCP Server。核心业务包含建书、世界观、角色、卷纲、章节管线、审计、truth、导出和短篇流程。如果 API 层直接写业务逻辑，后续多入口会互相复制状态机和错误处理。

## Decision

采用 Python FastAPI 作为 HTTP API 层，业务逻辑集中在 `src/storyforge3/services/`，并用 `services/protocols.py` 定义服务边界。FastAPI 路由只做参数校验、依赖注入、调用 service 和响应映射。

## Consequences

Service 可以被 CLI、Web、MCP 和桌面端复用，测试可以直接 mock Protocol。代价是接口数量较多，新增能力需要同步维护 service、protocol、route 和前端类型。

## Alternatives Considered

- Rust 全栈：性能强，但 LLM/Python 生态和已有审计逻辑迁移成本过高。
- Django：生态成熟，但对本地单用户工具偏重，service 边界反而容易被 ORM 牵引。
- FastAPI 路由直写业务：初期更快，但会让 Web/MCP/CLI 分叉，长期风险高。
