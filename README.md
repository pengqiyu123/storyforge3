# StoryForge3

StoryForge3 是面向中文网文生产的全流程创作引擎：从空白页创建书籍，生成世界观、角色、卷纲和章节，经过机械审计、LLM 审计、局部修订、truth 提取和多格式导出，最终产出可发布章节。

当前 P0 里程碑已达成：真实 provider `Codex 直连中转` / `gpt-5.5` 完整跑通 3 章连续生产 E2E，结果为 `3/3 exported`。

## 当前能力

- 章节生产：`plan -> draft(chunked) -> normalize -> audit -> revise(patch) -> truth_extract -> export`
- 长文生成：`ChunkedGenerator` 分块起草，避免一次性长生成超时
- 局部修订：find/replace patch revise，覆盖 spot/surgical 类问题
- 质量门禁：36 条机械审计规则、4 个 LLM 审计维度、5 种 revision mode
- 记忆系统：SQLite `truth_entries` + JSON 备份，支持跨章 relevance 检索
- 导出格式：番茄 TXT、Markdown 合集、EPUB、起点 TXT
- 服务层：11 个 Service Protocol，为 CLI、FastAPI、前端/桌面客户端复用准备
- API 层：FastAPI REST routes + SSE events，`storyforge3 serve` 启动
- Provider 管理：只读 CC-Switch SQLite provider，导入到 StoryForge3 本地配置后直连 provider API

## 验证基线

最新本地验证：

- `ruff check .` clean
- `pytest tests/ -q`：301 passed，1 个非阻塞 deprecation warning
- 覆盖率：约 91%
- Phase 4：原子写入、失败诊断持久化、Context source tracking、API 集成测试覆盖已完成
- 多章节 E2E：`books/e2e-multi-20260608-180847`
  - Chapter 1：2255 字，audit passed，1 次 patch revision，45 条 truth
  - Chapter 2：2706 字，audit passed，0 次 revision，74 条 truth
  - Chapter 3：2940 字，audit passed，0 次 revision，52 条 truth
  - 跨章 truth 检索通过

## 安装

```powershell
cd D:\python\Novel\storyforge3
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

或创建新环境：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## 常用命令

```powershell
# 单元测试
.\.venv\Scripts\python.exe -m pytest tests/ -q

# Lint
.\.venv\Scripts\ruff.exe check .

# 健康检查
.\.venv\Scripts\storyforge3.exe health

# 启动 API 服务
.\.venv\Scripts\storyforge3.exe serve

# 单章真实 LLM E2E
.\.venv\Scripts\python.exe scripts\e2e_test.py

# 3 章连续真实 LLM E2E
.\.venv\Scripts\python.exe scripts\e2e_multi_chapter.py
```

## 项目结构

```text
storyforge3/
├── src/storyforge3/
│   ├── api/              # FastAPI routes + SSE
│   ├── audit/            # 机械规则、revision mode、patch revise
│   ├── context/          # ContextBlock / ContextPackage 来源追踪
│   ├── export/           # Tomato TXT / Markdown / EPUB / Qidian TXT
│   ├── llm/              # Provider 配置、路由、重试、分块生成
│   ├── prompts/          # PromptRegistry 版本化模板
│   ├── services/         # Book/World/Character/Volume/Chapter/Truth/Export 等服务
│   ├── state/            # 章节状态机
│   ├── truth/            # SQLite truth database + retriever
│   └── workflow.py       # 章节生产管线
├── scripts/              # E2E 与诊断脚本
├── tests/                # 单元测试与 API 测试
├── docs/                 # 架构、差距分析、规则调研
├── AGENTS.md             # Codex 协作上下文
└── CLAUDE.md             # Claude Code 协作上下文
```

## Provider 配置

StoryForge3 不使用 CC-Switch local proxy。当前架构是：

```text
CC-Switch SQLite provider database
    -> CCSwitchDBReader 只读导入 provider
    -> .storyforge3/providers.json 保存 StoryForge3 本地选择
    -> LLMService 直连 provider API
```

当前验证 provider 示例：

- Provider：`Codex 直连中转`
- Base URL：`https://api.vip1129.cc`
- Model：`gpt-5.5`
- Primary route：`/v1/responses`

## 说明

`books/`、`.storyforge3/`、`.venv/`、日志和 coverage 文件属于本地运行产物，默认不纳入版本库。
