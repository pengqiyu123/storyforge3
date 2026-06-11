# Codex 指令：Phase 10A-1 — 覆盖率基线 + 文档治理

> 发出日期：2026-06-11
> 产品经理：Claude Code PM
> 执行者：Codex
> 前置条件：Phase 8.5 完成（486 后端 tests, 62 前端 tests, ruff clean, pnpm build clean）
> 战略来源：`docs/project-strategy.md` Phase A-3

## 任务概述

### 当前状态

- 引擎功能完整，Phase 1-8.5 共 26 个子阶段全部完成
- 后端 486 tests / 前端 62 tests / ruff clean / pnpm build clean
- **无覆盖率数字**：从未运行 `pytest --cov`，无法量化测试质量
- `project-status-and-forward-plan.md` 442 行，混合了状态/历史/计划三种职责
- `docs/adr/` 目录空置（仅 `.gitkeep`），关键架构决策无独立记录
- `架构决策-前端与规范.md` 存在但不是正式 ADR 格式

### 本阶段交付

**不写生产代码。** 只做三件事：

1. **覆盖率基线**：运行 `pytest --cov`，记录数字，写入状态文档
2. **文档拆分**：将 `project-status-and-forward-plan.md` 拆为 3 个独立文件
3. **ADR 启用**：补写 ≥5 个关键架构决策记录

## 核心决策

### 为什么先做文档治理而非直接写功能代码

Phase B（自动导演）需要可靠的工程基线。覆盖率数字是后续质量门禁的依据；拆分后的文档让维护者快速定位信息；ADR 让架构决策可追溯——这些是后续阶段的基础设施。

### 为什么不使用 pytest-cov 的 HTML 报告

CI 环境不需要可视化报告。`--cov-report=term-missing` 在终端输出即可，数字记入文档。如果后续需要 HTML 报告可以随时加。

## Part 1：覆盖率基线

### 1.1 安装 pytest-cov

```bash
pip install pytest-cov
```

确认 `pyproject.toml` 的 `[project.optional-dependencies]` 或 dev dependencies 包含 `pytest-cov`。如果没有，添加它。

### 1.2 运行覆盖率

```bash
cd storyforge3
.\.venv\Scripts\python.exe -m pytest tests/ --cov=src/storyforge3 --cov-report=term-missing -q
```

记录以下数字：
- **总体覆盖率百分比**（如 `TOTAL ... 78%`）
- **各模块覆盖率**（services/ audit/ truth/ llm/ 等关键目录）
- **缺失覆盖率最高的 3 个文件**

### 1.3 将数字写入文档

在拆分后的 `docs/current.md`（见 Part 2）的"质量基线"章节中添加覆盖率表：

```markdown
### 测试覆盖率基线（Phase 10A-1 记录）

| 模块 | 覆盖率 | 缺失 Top 文件 |
|------|--------|-------------|
| 总体 | XX% | — |
| services/ | XX% | ... |
| audit/ | XX% | ... |
| truth/ | XX% | ... |
| llm/ | XX% | ... |
```

## Part 2：文档拆分

### 2.1 拆分 `project-status-and-forward-plan.md`

将 442 行单文件拆为 3 个文件，各自职责明确：

#### `docs/current.md`（~150 行）

**内容来源**：原文件 §一（项目现状总览）+ §二（健康审计结论）

必须包含：
- 已交付阶段总表（Phase 1-8.5，紧凑表格）
- 代码量统计（更新为最新数字：101 Python 文件/11,986 行 + 104 React 文件/7,048 行）
- 质量基线（tests 数 + ruff + build + **覆盖率数字**）
- 健康审计结论摘要
- 当前战略阶段：Phase A（验证期）

#### `docs/history.md`（~200 行）

**内容来源**：原文件 §四（推荐后续计划）中的已交付阶段记录

必须包含：
- Phase 7A-1 到 Phase 8.5 的完成记录（每个阶段 3-5 行摘要）
- 每个阶段的关键交付件和测试增量
- 倒序排列（最新的在上面）

#### `docs/next.md`（~80 行）

**内容来源**：原文件 §五（风险矩阵）+ 战略路线图

必须包含：
- Phase 10A 路线图（Phase A 的 3 个子阶段 + 验收标准）
- Phase 10B 规划概要（自动导演 MVP）
- Phase 10C 规划概要（RAG + 方法论 + 产品化）
- 风险矩阵（从 `project-strategy.md` §七提取）
- Phase A 量化目标表（从 `project-strategy.md` 附录 B 提取）

### 2.2 删除原文件

拆分完成后删除 `docs/project-status-and-forward-plan.md`。

### 2.3 更新引用

搜索所有引用 `project-status-and-forward-plan.md` 的文件，更新为新的文件路径。至少检查：
- `CLAUDE.md`
- `docs/pm-process.md`
- `docs/project-strategy.md`
- 其他 directives 中的引用

## Part 3：ADR 启用

### 3.1 ADR 模板

在 `docs/adr/` 下创建 `TEMPLATE.md`（供后续 ADR 参考）：

```markdown
# ADR-{number}: {title}

## Status
[Accepted]

## Context
[What is the issue that motivated this decision?]

## Decision
[What is the change that we're proposing/making?]

## Consequences
[What becomes easier or more difficult?]

## Alternatives Considered
[What other options did we consider?]
```

### 3.2 补写 5 个关键 ADR

根据代码库分析，以下 5 个是最需要记录的架构决策（优先级排序）：

#### ADR-001：FastAPI + Service Protocol 分层架构

- **决策**：Python FastAPI 作为 API 层，14 个 Service Protocol 接口约束业务逻辑，支持 CLI/Web/Desktop 多前端
- **替代方案**：Rust 全栈（研究后否决：Python LLM 生态优势）、Django（太重）
- **后果**：开发效率高，测试友好；牺牲了 Rust 级性能
- **证据**：`src/storyforge3/services/protocols.py`、`src/storyforge3/api/app.py`

#### ADR-002：React 19 + Vite + shadcn/ui 前端

- **决策**：React 19 + Vite 7 + TypeScript + Tailwind 4 + shadcn/ui
- **替代方案**：Vue 3 + Element Plus（参考项目评分 D+）、纯 CLI 无前端
- **后果**：现代开发体验，组件库成熟；需要 Node.js 工具链
- **证据**：`web/package.json`、`docs/架构决策-前端与规范.md`

#### ADR-003：Truth 系统 — SQLite 结构化事实存储

- **决策**：SQLite `truth_entries` 存储结构化事实（6 类），JSON 备份，关键词检索（中文 n-gram + 复合评分）
- **替代方案**：纯 Markdown（查询慢）、JSON-only（无搜索能力）、RAG 向量检索（基础设施成本高，当前不需要）
- **后果**：单书场景检索够用，未来 50+ 章可能需要补充语义检索
- **证据**：`src/storyforge3/truth/store.py`、`src/storyforge3/truth/retriever.py`

#### ADR-004：Tauri 2 + PyInstaller Sidecar 桌面分发

- **决策**：Tauri 2 做 UI 壳（Rust），PyInstaller `--onedir` 打包 Python 后端为 sidecar
- **替代方案**：Electron（150MB+ 打包）、纯 Tauri（需 Rust 重写后端）、Nuitka（未验证）
- **后果**：用户无需安装 Python；打包体积比纯 Tauri 大，但远小于 Electron
- **证据**：`src-tauri/tauri.conf.json` externalBin 配置、`scripts/desktop_entry.py`

#### ADR-005：CC-Switch 只读集成 + 双层 Provider 路由

- **决策**：CC-Switch SQLite 数据库只读访问，导入到 `.storyforge3/providers.json`；LLMService 支持 4 种 API 协议
- **替代方案**：SF3 自建 Provider 管理（重复造轮子）、硬编码 Provider（不灵活）
- **后果**：Provider 管理委托给 CC-Switch，SF3 聚焦创作功能；需要 CC-Switch 先运行
- **证据**：`src/storyforge3/llm/ccswitch_reader.py`、`src/storyforge3/llm/llm_service.py`

### 3.3 每个 ADR 的要求

- 篇幅控制在 30-50 行
- Status 填 `Accepted`
- Context 必须说明"当时面临的选择压力"
- Alternatives Considered 必须列出 ≥2 个替代方案及其否决理由
- 不需要写 Consequences 中"尚未发生"的部分，只记录已知后果

## Part 4：借鉴来源

### 文档结构借鉴

| 借鉴内容 | 来源文件 | 借鉴方式 | 新写比例 |
|---------|---------|---------|---------|
| ADR 模板格式 | `~/.claude/rules/patterns/templates.md` ADR Template | 直接移植：复制模板格式，填入 SF3 内容 | ≤20% |
| 架构决策背景 | `docs/架构决策-前端与规范.md` | 骨架移植：提取决策要点，重组为 ADR 格式 | 30% |
| 状态文档拆分模式 | `storyforge/` 的分层文件架构（三层内容模型） | 模式复用：按职责拆分的思路 | 40% |
| 覆盖率报告 | 无——pytest-cov 标准输出 | 新写：只是记录数字 | 80% |

### 无直接来源说明

- ADR 内容：决策散落在 CLAUDE.md、directives、`架构决策-前端与规范.md` 中，无现成 ADR 格式文件。需要从多源提取。
- 文档拆分：`project-status-and-forward-plan.md` 是 SF3 特有的状态文档，拆分方式需要根据实际内容调整。

## 验收标准

### 覆盖率基线

- [ ] `pytest --cov=src/storyforge3` 成功运行并输出覆盖率报告
- [ ] 覆盖率数字已记录到 `docs/current.md`
- [ ] `pytest-cov` 已添加到项目依赖（dev/optional）

### 文档拆分

- [ ] `docs/current.md` 存在，≤200 行，包含质量基线 + 已交付阶段表
- [ ] `docs/history.md` 存在，≤250 行，包含已交付阶段详细记录
- [ ] `docs/next.md` 存在，≤150 行，包含 Phase 10A 路线图 + 风险矩阵
- [ ] `docs/project-status-and-forward-plan.md` 已删除
- [ ] 所有引用原文件的地方已更新

### ADR 启用

- [ ] `docs/adr/TEMPLATE.md` 存在
- [ ] `docs/adr/ADR-001-fastapi-service-protocol.md` 存在
- [ ] `docs/adr/ADR-002-react-vite-frontend.md` 存在
- [ ] `docs/adr/ADR-003-truth-sqlite-storage.md` 存在
- [ ] `docs/adr/ADR-004-tauri-pyinstaller-sidecar.md` 存在
- [ ] `docs/adr/ADR-005-ccswitch-read-only-integration.md` 存在
- [ ] 每个 ADR 包含 Status / Context / Decision / Consequences / Alternatives 五个章节

### 质量门禁

- [ ] `pytest tests/ -q` 全绿，无退步（基线 486）
- [ ] `ruff check .` clean
- [ ] `pnpm test` 全绿（基线 62）
- [ ] `pnpm build` 通过
- [ ] 无新 `TODO` / `FIXME` 残留

### 文档更新

- [ ] `CLAUDE.md` 更新：Phase 10A-1 完成记录 + 覆盖率数字 + 引用路径更新
- [ ] `docs/next.md` 反映 Phase 10A 路线图

## 估算工作量

| 文件 | 估算行数 | 说明 |
|------|---------|------|
| `docs/current.md` | ~150 行 | 新建，从原文件提取 |
| `docs/history.md` | ~200 行 | 新建，从原文件提取 |
| `docs/next.md` | ~80 行 | 新建，从战略文档提取 |
| `docs/adr/TEMPLATE.md` | ~20 行 | 新建 |
| `docs/adr/ADR-001` ~ `ADR-005` | 5 × ~40 = 200 行 | 新建 |
| `pyproject.toml` | ~2 行 | 添加 pytest-cov 依赖 |
| **合计** | **~650 行** | 纯文档，不涉及生产代码 |

## 不做的事（Out of Scope）

- ❌ 不写生产代码
- ❌ 不修改任何 `src/` 下的代码
- ❌ 不做覆盖率提升（只记录基线数字）
- ❌ 不写超过 5 个 ADR（其余在后续阶段补充）
- ❌ 不修改测试文件
- ❌ 不修改前端代码
