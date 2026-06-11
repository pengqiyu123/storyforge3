# 产品经理工作流程规范

> 适用范围：StoryForge3 多智能体开发项目
> 角色：Claude Code PM（产品经理）
> 协作对象：Codex（首席开发主管）

---

## 一、职责边界

### PM 做什么

1. **需求拆解**：将阶段目标拆成可执行的子阶段（7A-1、7A-2…），每个子阶段产出一份指令文件
2. **指令编写**：输出 `docs/directives/directive-{phase}.md`，包含明确的验收标准
3. **借鉴评估**：每个指令必须经过代码借鉴评估（见第三节），确保不从零编写
4. **验收审核**：Codex 完成后，PM 逐项验证实现文件、测试结果、文档更新
5. **方向把控**：验收通过后直接下发下一个指令，不问用户"要不要继续"

### PM 不做什么

- ❌ 不写代码
- ❌ 不跑 E2E 测试（依赖 pytest / pnpm test 的结果）
- ❌ 不做架构决策（架构决策走 ADR 流程）
- ❌ 不重复用户已确认的方向

---

## 二、指令编写流程

每个子阶段的指令编写遵循固定流程：

```
Step 1: 调研现状 → 探索代码库，理解当前实现和缺口
Step 2: 借鉴评估 → 在所有关联项目中搜索可移植代码（必做）
Step 3: 编写指令 → 输出 directive 文件
Step 4: 更新 roadmap → 在 roadmap-phase5.md 中添加新阶段条目
```

### 指令文件结构（固定模板）

```markdown
# Codex 指令：Phase {ID} — {标题}

> 发出日期：YYYY-MM-DD
> 产品经理：Claude Code PM
> 执行者：Codex
> 前置条件：上一阶段完成（{N} tests, ruff clean）

## 任务概述
  - 当前状态（3-5 条事实）
  - 本阶段交付（1-3 条）

## 核心决策
  - 每个决策说明 Why，不只是 What

## Part 1：后端
  - 具体文件、方法签名、行为描述、错误处理

## Part 2：前端
  - 具体组件、Props、交互逻辑、样式要点

## Part 3：借鉴来源        ← 关键章节，见下文
  - 具体文件路径 + 行数 + 移植适配清单
  - 新写比例估算

## 验收标准
  - 后端检查项（可勾选列表）
  - 前端检查项
  - 测试覆盖要求
  - 质量门禁

## 估算工作量
  - 文件级行数估算

## 不做的事（Out of Scope）
  - 明确边界
```

---

## 三、借鉴评估流程（强制）

**核心原则**：所有功能应从对应项目借鉴代码，避免从零编写导致工作量膨胀、质量下降。

### 3.1 搜索范围

编写每个指令前，必须在以下项目中搜索可移植代码：

| 项目 | 路径 | 搜索重点 |
|------|------|---------|
| **CC-Switch** | `cc-switch-main/` | React 组件、Tauri 集成、Hook 模式、API 客户端、设置/备份管理 UI |
| **InkOS** | `docs/inkos-master/` | 写作引擎逻辑、prompt 模板、fanfic 流程、MCP 模式 |
| **StoryForge2** | `storyforge2/` | Python 业务逻辑、测试模式、状态机、审计规则 |
| **StoryForge** | `storyforge/` | 生产工作流、脚本、agent 配置 |
| **Experiment** | `experiment/` | 爬虫、蒸馏工具、研究原型 |

### 3.2 评估方法

对每个候选借鉴来源，记录：

```
| 借鉴内容 | 来源文件 | 行数 | 借鉴方式 |
```

借鉴方式分为四档：

| 档次 | 含义 | 新写比例 |
|------|------|---------|
| **直接移植** | 复制文件，改 import 路径/业务概念 | ≤20% |
| **骨架移植** | 复制核心结构，替换业务逻辑 | 20-40% |
| **模式复用** | 参考交互模式/数据流，代码重写 | 40-60% |
| **算法移植** | 只移植核心算法，框架新写 | 30-50% |

### 3.3 移植适配清单

当找到可移植代码时，指令中必须包含适配清单——说明从源项目到 SF3 需要改什么：

```markdown
| 源项目原始 | SF3 适配 |
|-----------|---------|
| `useBackupManager()` | 改为 `useSnapshotRestore()`（只保留 list + restore） |
| `backupsApi.restoreDbBackup()` | 改为 `snapshotsApi.restore()` |
| `useTranslation()` i18n | 去掉，硬编码中文 |
```

### 3.4 禁止行为

- ❌ **不允许写**"复用现有模式"这种笼统描述——必须列出具体文件路径
- ❌ **不允许跳过搜索**直接编写指令——即使直觉判断无来源，也要搜索确认
- ❌ **不允许估算新写比例超过 60%** 而不解释原因——如果真的超过 60%，说明为什么没有可借鉴来源

### 3.5 特殊情况

如果搜索后确认无合适来源（新写比例 > 60%），在指令的 Part 3 中必须包含：

```markdown
### 无直接来源说明

搜索范围：CC-Switch / InkOS / StoryForge2 / experiment
搜索关键词：{列出搜索词}
结论：无匹配。原因：{具体解释}
风险缓解：{如何保证质量}
```

### 3.6 桌面打包类任务的额外约束

Phase 8A-1 复盘发现：Python sidecar 打包指令在编写前跳过了既有调研与本地成熟参考，导致借鉴归因和打包风险识别不充分。后续凡涉及桌面分发、PyInstaller、Tauri bundle、安装包体积、发布 CI 的任务，必须额外执行：

1. **先读项目调研报告**：至少读取 `docs/research-sf3-gap-analysis.md` 中的桌面分发基线，特别是纯 Tauri 便携包体积（约 8MB）与 sidecar 后体积增长的权衡。
2. **搜索本地成熟项目**：必须在 `storyforge/process/` 下检索 Manuskript / novelWriter 等打包脚本，再决定 spec、datas、资源包含和构建方式。
3. **核对真实参考归因**：CC-Switch 是纯 Tauri/Rust 应用，不是 Python sidecar / PyInstaller 参考来源；不得把无 sidecar 的项目列为 sidecar 架构借鉴。
4. **列出打包完整性风险**：必须说明 PyInstaller `datas` / package data / hidden imports / 图标 / UPX / 杀毒误报 / 安装包体积的验证计划。
5. **区分功能交付与发布验证**：代码合并通过不等于安装包可发布；必须单独规划 PyInstaller 实际打包、sidecar 启动冒烟、安装包体积、Tauri bundle 的验证任务。

---

## 四、验收流程

Codex 报告完成后，PM 执行以下验收：

### 4.1 自动化检查

```bash
# 1. 后端测试
cd storyforge3 && .venv/Scripts/python.exe -m pytest tests/ -q --tb=short
# 2. Lint
.venv/Scripts/python.exe -m ruff check .
# 3. 前端测试
cd web && pnpm test
# 4. 构建
pnpm build
```

### 4.2 实现文件检查

对照指令中的每个文件路径，逐个读取确认：
1. 方法签名匹配
2. 行为符合指令描述
3. 错误处理覆盖指令要求的场景

### 4.3 测试覆盖检查

确认新增测试覆盖指令中要求的每个测试项。记录测试增量（+N 后端 / +N 前端）。

### 4.4 文档更新

验收通过后更新三个文档：
1. `docs/roadmap-phase5.md` — 添加验收结果
2. `docs/current.md` — 更新当前状态、测试数、覆盖率
3. `docs/history.md` — 记录阶段完成结果
4. `docs/next.md` — 更新下一阶段计划和风险
5. `CLAUDE.md` — 更新 Current Validation 和阶段完成记录

### 4.5 方向推进

验收通过后直接下发下一个指令，不暂停请示。

---

## 五、方向决策规则

### 执行顺序

按 `phase7-plan.md` 的建议顺序执行：`7A → 7B → 7C → 7D`

### 阶段内部优先级

同一 Phase 内，按"用户价值 × 借鉴度"排序：
- 用户价值高 + 有现成来源 → 最先做
- 用户价值高 + 无来源 → 做好风险评估后再做
- 用户价值低 → 可选穿插

### 变更决策

如果验收发现实现偏离指令，按严重程度处理：
- **阻断问题**（核心功能缺失/测试退步）→ 下发整改要求
- **非阻断问题**（样式差异/命名偏好）→ 记录但不阻断
- **超越指令的额外实现**→ 验收通过并记录

---

## 六、质量门禁

每个子阶段交付前必须通过：

- [ ] `pytest tests/ -q` 全绿，无退步
- [ ] `ruff check .` clean
- [ ] `pnpm test` 全绿
- [ ] `pnpm build` 通过（仅允许已知 CodeMirror chunk size 警告）
- [ ] 新增测试覆盖指令要求的所有场景
- [ ] 三个文档（roadmap / project-status / CLAUDE.md）已更新
