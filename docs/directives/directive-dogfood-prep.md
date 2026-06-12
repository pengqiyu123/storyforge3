# Codex 指令：Dogfood 准备与执行支持

> 发出日期：2026-06-12
> 产品经理：Claude Code PM
> 执行者：Codex
> 前置条件：Phase 10A 全部完成（HEAD `275af86`，501 后端 + 71 前端 + build clean）
> 战略来源：PM 修正方案，dogfood 是 Phase 10B 的前置门禁

## 任务概述

### 决策背景

Phase 10A 工程验证已全部完成，但尚未经过人在 Web UI 上的真实创作验证。PM 决定在进入 Phase 10B（自动导演 MVP）之前，先执行两轮 dogfood，分别验证"复杂续写"和"从零开书"两种场景。

Codex 的职责是**准备系统、验证数据完整性、创建记录模板**，确保 dogfood 执行时系统处于最佳状态。

### 当前《别打了》数据状态

```
books/别打了w帮你们翻译还不行吗_20260611/
├── book.json          # book_id, title, genre=玄幻, target_chapters, status
├── world.json         # 9 rules, setting=雾桥城, power_system=文明力
├── characters.json    # 4 characters（沈听澜、赫鲁、伊芙蕾、秦缝）
├── volumes.json       # 卷纲
├── context.md         # 上下文
├── chapters/
│   └── 0001.md        # 第 1 章，2023 字
├── truth/
│   └── chapter-0001.json  # 11 facts + 4 char_updates + 4 rel_updates + 5 hooks + 4 irreversible_facts
├── docs/              # world-outline-review.md + world-outline-pm-notes.md
├── exports/
└── state/
```

## Part 1：系统健康验证

### 1.1 后端启动验证

```powershell
cd D:\python\Novel\storyforge3
.\.venv\Scripts\python.exe -m storyforge3 health
```

确认：
- [ ] `storyforge3 health` 通过
- [ ] Provider 连通（当前活跃 provider 应为可用状态）
- [ ] SQLite 数据库可读写

### 1.2 数据完整性检查

验证《别打了》数据在 storage 中可正常读写：

1. 确认 book 可通过 API 查询（`GET /api/books/{book_id}`）
2. 确认第 1 章可通过 API 读取（`GET /api/books/{book_id}/chapters/1`）
3. 确认 truth 可通过 API 读取（`GET /api/books/{book_id}/truth?chapter_no=1`）
4. 确认 world / characters 可通过 API 读取

如果任一 API 返回 404 或数据缺失，需要修复后再继续。

### 1.3 前端构建验证

```powershell
cd web
pnpm build
pnpm test
```

确认：
- [ ] `pnpm build` 通过（仅允许已有 CodeMirror chunk 警告）
- [ ] `pnpm test` 71 passed

### 1.4 后端测试验证

```powershell
.\.venv\Scripts\python.exe -m pytest --tb=no -q
```

确认：
- [ ] 501 passed，0 failed

## Part 2：Dogfood 记录模板创建

### 2.1 创建 dogfood runs 目录

在 `docs/dogfood-runs/` 下创建两个记录模板：

### 2.2 Round 1 模板：`docs/dogfood-runs/2026-06-12-biedale-chapter2.md`

```markdown
# Dogfood Run: 《别打了》第 2 章续写

## 基本信息

| 项目 | 内容 |
|------|------|
| 测试日期 | |
| 测试者 | |
| 书籍 | 别打了，我帮你们翻译还不行吗? |
| 章节 | 第 2 章（续写） |
| Provider / Model | |
| 后端版本 | 275af86 |
| 前端版本 | 275af86 |

## 前置数据

| 项目 | 值 |
|------|-----|
| 第 1 章字数 | 2023 |
| 第 1 章 truth 条目 | 11 facts + 4 char + 4 rel + 5 hooks + 4 irreversible |
| 世界观 rules | 9 条 |
| 核心角色 | 4 人 |

## 时间记录

| 步骤 | 开始时间 | 结束时间 | 耗时 | 结果 |
|------|----------|----------|------|------|
| plan | | | | |
| draft | | | | |
| audit | | | | |
| revise | | | | |
| truth | | | | |
| export | | | | |

## 进度 UI 观察

| 项目 | 观察 |
|------|------|
| draft 期间进度条是否显示 | |
| 进度条显示什么内容（段落数/阶段名） | |
| 进度更新是否流畅（不卡顿/不跳变） | |
| 错误或超时时进度条是否正确展示 | |
| 进度条消失时机是否正确 | |

## Truth 召回观察

| 项目 | 观察 |
|------|------|
| 第 2 章 draft 上下文中是否包含第 1 章 truth | |
| 召回了哪些关键事实 | |
| 召回内容对第 2 章创作是否有帮助 | |
| 是否有遗漏的关键事实未被召回 | |

## 章节质量评估

| 维度 | 评分(1-5) | 备注 |
|------|-----------|------|
| 设定一致性（12 文明体系是否保持） | | |
| 角色区分度（4 角色是否各有特色） | | |
| 情节推进（是否有实质进展） | | |
| 文风质量（是否流畅可读） | | |
| 字数达标（2000-3000 中文字） | | |

## 审计质量

| 项目 | 观察 |
|------|------|
| 机械审计命中了哪些规则 | |
| 命中是否合理 | |
| 是否有误判（不应命中的被命中） | |
| 是否有漏判（应该命中的未命中） | |
| LLM 审计 4 维度评价如何 | |

## 修订质量（如触发）

| 项目 | 观察 |
|------|------|
| 修订模式选择是否合理 | |
| 修订后是否改善了问题 | |
| 修订是否引入了新问题 | |

## 问题列表

| # | 严重度 | 问题描述 | 复现步骤 | 修复建议 |
|---|--------|---------|---------|---------|
| 1 | P0/P1/P2 | | | |

## 总体判定

- [ ] 可继续使用
- [ ] 需要修复后再用
- [ ] 阻断

## 是否愿意继续写第 3 章

（是 / 否 / 条件）

## 对 Phase 10B 的输入

基于本轮 dogfood，Phase 10B AutoDirector 应该：
1. ...
2. ...
```

### 2.3 Round 2 模板：`docs/dogfood-runs/2026-06-12-newbook-chapter1.md`

```markdown
# Dogfood Run: 新书从零创建 → 第 1 章

## 基本信息

| 项目 | 内容 |
|------|------|
| 测试日期 | |
| 测试者 | |
| 书籍 | （新建书名） |
| 章节 | 第 1 章（从零） |
| Provider / Model | |
| 后端版本 | 275af86 |
| 前端版本 | 275af86 |

## 开书流程

| 步骤 | 是否通过 Web UI 完成 | 耗时 | 观察 |
|------|---------------------|------|------|
| 创建书籍 | | | |
| 设定世界观 | | | |
| 创建角色 | | | |
| 规划卷纲 | | | |
| 第 1 章 plan | | | |
| 第 1 章 draft | | | |

## 开书体验观察

| 项目 | 观察 |
|------|------|
| 创建书籍流程是否顺畅 | |
| 世界观编辑是否方便 | |
| 角色创建是否方便 | |
| 卷纲规划是否直观 | |
| 从建书到第一次 draft 之间需要多少步操作 | |

## 时间记录

| 步骤 | 开始时间 | 结束时间 | 耗时 | 结果 |
|------|----------|----------|------|------|
| plan | | | | |
| draft | | | | |
| audit | | | | |
| revise | | | | |
| truth | | | | |
| export | | | | |

## 章节质量评估

| 维度 | 评分(1-5) | 备注 |
|------|-----------|------|
| 设定一致性 | | |
| 角色区分度 | | |
| 情节吸引力 | | |
| 文风质量 | | |
| 字数达标 | | |

## 问题列表

| # | 严重度 | 问题描述 | 复现步骤 | 修复建议 |
|---|--------|---------|---------|---------|
| 1 | P0/P1/P2 | | | |

## 总体判定

- [ ] 可继续使用
- [ ] 需要修复后再用
- [ ] 阻断

## 对 Phase 10B AutoDirector 的输入

从零开书体验中，AutoDirector 应该自动化的步骤：
1. ...
必须保留人工确认的步骤：
1. ...
```

## Part 3：文档同步

### 3.1 更新 CLAUDE.md

更新 `storyforge3/CLAUDE.md` 中 Current Validation 部分：

1. 后端测试基线：498 → 501
2. 前端测试基线：62 → 71
3. Phase 10A-3 状态：从 in progress 改为 complete
4. 新增 Phase 10A-Dogfood 状态说明

### 3.2 提交

所有文档变更（current.md、next.md、dogfood 模板、CLAUDE.md）一起提交：

```
docs: add dogfood preparation templates and update plan for Phase 10A-Dogfood
```

## 验收标准

### 功能检查

- [ ] `storyforge3 health` 通过
- [ ] 《别打了》book / chapter 1 / truth / world / characters 全部可通过 API 读取
- [ ] `pnpm test` 71 passed
- [ ] `pytest` 501 passed
- [ ] `pnpm build` 通过
- [ ] 两个 dogfood 记录模板已创建在 `docs/dogfood-runs/`
- [ ] CLAUDE.md 基线数字已更新

### 文档检查

- [ ] `docs/current.md` 反映 10A 全部完成 + dogfood 为当前焦点
- [ ] `docs/next.md` 包含 10A-Dogfood → 10B-1a → 10B-1b 路线图
- [ ] CLAUDE.md 基线与实际测试结果一致

## 不做的事（Out of Scope）

- ❌ 不修改后端代码（系统已通过 Phase 10A 验证）
- ❌ 不修改前端代码
- ❌ 不执行 dogfood（dogfood 由 PM 和用户在 Web UI 上执行）
- ❌ 不创建新书籍（由用户在 dogfood 时创建）
- ❌ 不运行 E2E 脚本（dogfood 必须通过 Web UI 真实体验）

## 估算工作量

| 文件 | 估算行数 | 说明 |
|------|---------|------|
| `docs/dogfood-runs/2026-06-12-biedale-chapter2.md` | ~120 行 | 新建 |
| `docs/dogfood-runs/2026-06-12-newbook-chapter1.md` | ~80 行 | 新建 |
| `docs/current.md` | ~10 行修改 | 状态更新 |
| `docs/next.md` | 已由 PM 更新 | — |
| `CLAUDE.md` | ~5 行修改 | 基线数字更新 |
| **合计** | **~215 行** | 纯文档 |
