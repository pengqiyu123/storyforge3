# StoryForge3 当前状态

> 更新时间：2026-06-12  
> 职责：只记录当前事实、质量基线和进行中阶段。历史流水见 `docs/history.md`，后续计划见 `docs/next.md`。

## 当前定位

StoryForge3 是 AI Native 中文网文全流程生产工作台，覆盖建书、世界观、角色、卷纲、章节起草、审计、修订、truth 提取、导出、桌面端和 MCP 集成。

当前战略阶段是 **Phase 10A-Dogfood**：Phase 10A 工程验证已完成（文档治理、流式后端、前端进度 UI），进入 dogfood 产品体验验证阶段。两轮 dogfood 完成后再设计 Phase 10B 指令。

## 已交付阶段

| 阶段 | 交付内容 | 状态 |
|------|----------|------|
| Phase 1-4 | 后端引擎、API、安全网、审计、Truth、Context 跟踪 | 完成 |
| Phase 5A | React/Vite 前端 MVP | 完成 |
| Phase 5C | JSONL 日志、Service 对齐、快照 | 完成 |
| Phase 6 | CodeMirror、Tauri、同人、短篇、MCP Server | 完成 |
| Phase 7A | 写作工作台：编辑保存、审计定位、修订 Diff | 完成 |
| Phase 7B | 质量运营：Truth 面板、快照管理、导出预览 | 完成 |
| Phase 7C | MCP 实战化：错误建议、tool 描述、注册文档 | 完成 |
| Phase 7D | CI/CD、签名骨架、用户数据管理 | 完成 |
| Phase 8 | PyInstaller sidecar、Service 测试补齐 | 完成 |
| Phase 8.5 | Dogfood RC 文档和冷启动验证 | 完成 |
| Phase 9 | Prompt 质量修复 | 完成 |
| Phase 10A-1 | 覆盖率基线、文档拆分、ADR 启用 | 完成 |
| Phase 10A-2 | 后端 LLM 流式输出、SSE 进度、dogfood 修复 | 完成 |
| Phase 10A-3 | 前端 SSE 进度 UI | 完成 |

## 代码量

| 层 | 文件数 | 代码行数 |
|----|--------|----------|
| Python 后端 `src/` | 101 | 10,256 |
| React 前端 `web/src` | 104 | 6,324 |
| Rust 桌面壳 `src-tauri/src` | 4 | 436 |

## 质量基线

| 项 | 当前记录 |
|----|----------|
| 后端测试 | 501 passed, 1 warning（Phase 10A-2 MEDIUM-1 后基线） |
| 前端测试 | 71 passed（Phase 10A-3 后基线） |
| Rust 测试 | 5 既有基线；本机无 Rust 时需在 CI 验证 |
| Python lint | `ruff check .` clean |
| Frontend build | `pnpm build` clean，仅 CodeMirror 大 chunk 警告 |
| 覆盖率 | 91% total |

### 测试覆盖率基线（Phase 10A-1）

命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\ --cov=src/storyforge3 --cov-report=term-missing -q
```

结果：`498 passed, 1 warning`，`TOTAL 6234 stmts / 562 miss / 91%`。

| 模块 | 覆盖率 | 缺失 Top 文件 |
|------|--------|---------------|
| 总体 | 91% | `mcp/__main__.py` 0%, `mcp/server.py` 57%, `__main__.py` 65% |
| services/ | 90% | `workspace_service.py` 82%, `export_service.py` 83%, `chapter_service.py` 86% |
| audit/ | 91% | `revision_diff.py` 74%, `revision_modes.py` 89%, `revision_patch.py` 89% |
| truth/ | 97% | `store.py` 96%, `database.py` 98%, `extractor.py` 98% |
| llm/ | 89% | `llm_service.py` 86%, `ccswitch_db_reader.py` 87%, `client.py` 92% |

## 健康审计摘要

整体评级：A-（Green，附 Yellow 建议）。核心结论：

- Service Protocol 分层执行良好，API/Web/MCP/Tauri 均围绕服务层消费。
- Truth 系统已形成 SQLite + JSON 备份 + 可视化面板闭环。
- 36 条机械审计、LLM 审计、段落定位、修订 Diff 已形成可用质量循环。
- Tauri + PyInstaller sidecar 提供桌面分发路径，但真实打包体积和 sidecar 启动仍需发布前验证。
- 最大产品风险仍是真实 dogfood 样本不足，以及长线复杂世界观下 Truth 检索退化。

## 当前工作焦点

1. 执行 Dogfood Round 1：《别打了》第 2 章续写验证（复杂世界观 + truth 召回 + 进度 UI）。
2. 执行 Dogfood Round 2：新书从零创建验证（建书 → world → characters → volume → 第 1 章）。
3. 基于两轮 dogfood 结果设计 Phase 10B AutoDirector 指令。
