# Codex 指令：Phase 8.5 — Dogfood RC

> 发出日期：2026-06-11
> 产品经理：Claude Code PM
> 执行者：Codex
> 前置条件：Phase 8 完成（468 后端 tests, 62 前端 tests, ruff clean, pnpm build clean）

## 任务概述

### 当前状态

- 引擎功能完整：plan → draft → audit → revise → truth → export 全链路已通过 E2E 验证（3 章节）
- Web 前端完整：59 源文件，14 页面/组件，62 测试，覆盖书籍/章节/审计/真相/快照/导出/设置
- Tauri 桌面壳代码就绪但**从未在真实环境启动过**
- PyInstaller sidecar 脚本就绪但**从未实际打包验证**
- **没有用户-facing 文档**：无 README.md，无 quickstart，新用户无法自行启动

### 本阶段交付

**不加新功能。** 只做三件事：

1. **用户文档**：让一个全新的开发者能在 10 分钟内跑起 `storyforge3 serve` + Web 前端
2. **启动修错**：按文档走一遍，遇到阻塞问题就修，让 `storyforge3 serve` → 浏览器 → 创建书籍 → 跑管线 这条路无障碍
3. **Dogfood 协议**：定义"真实写一章"的测试协议和问题记录模板

## 核心决策

### 为什么不是继续做新功能

引擎 Phase 1-8 累计 16,400+ 行代码、530+ 测试，但没有一个人用它写过一章真实的小说。Dogfood 反馈比任何新功能都紧迫。写一章真实内容暴露的问题，可能比 10 个规划阶段发现的都多。

### 为什么先 Web 不先桌面

`storyforge3 serve` + `pnpm dev` 是最短路径——跳过 Rust 工具链安装、PyInstaller 打包、sidecar 路径等不确定因素。桌面壳作为并行验证路径，不阻塞使用。

## Part 1：用户文档

### 1.1 创建 `README.md`

在 `storyforge3/` 根目录创建 `README.md`，中文撰写，结构参考 `storyforge2/README.md` 的"快速开始"模式。

**必须包含的章节：**

```markdown
# StoryForge3

中文网文全流程创作引擎 — 从空白页到成书，AI 辅助 + 36 条机械审计 + 多模式修订。

## 快速开始

### 环境要求
- Python ≥ 3.11
- Node.js ≥ 18（前端开发）
- pnpm（前端包管理）
- CC-Switch（AI 提供商管理，可选）

### 后端启动
（步骤：创建 venv → pip install → storyforge3 serve → 验证 health 端点）

### 前端启动
（步骤：cd web → pnpm install → pnpm dev → 打开浏览器）

### 配置 AI 提供商
（CC-Switch 导入 或 手动创建 .storyforge3/providers.json 的最小示例）

### 第一个章节
（Web UI 操作：创建书籍 → 构建世界观 → 创建角色 → plan → draft → audit → export）

## 核心能力
（表格：36 机械规则 / 5 修订模式 / 4 导出格式 / MCP Server / 短篇管线 等）

## 目录结构
（src/ web/ src-tauri/ docs/ books/ 的简要说明）

## 开发
（pytest / ruff / pnpm test / pnpm build / MCP 注册 命令速查）

## 许可
```

**关键要求：**
- "快速开始"章节的每一步都必须是可复制粘贴执行的命令
- `providers.json` 必须给出一个**最小可运行示例**（一个 provider 的 JSON 结构）
- 每个步骤后面跟一个**验证命令**（如 `curl http://localhost:8000/api/health`），让用户确认成功
- 不提 Tauri 桌面壳、PyInstaller sidecar——那些是进阶话题，不属于快速开始

### 1.2 创建 `docs/quickstart.md`

README 的扩展版。包含 README 省略的细节：

- CC-Switch 安装和配置的详细步骤
- `.storyforge3/providers.json` 的完整 schema 说明
- `StoryForge3Config` 所有环境变量的说明（从 `config.py` 提取）
- 常见问题排查（参考 `docs/architecture/mcp-registration.md` 的"故障排查"章节格式）
- 从零到第一章的完整操作截图（文字描述即可，不需要实际截图）

### 1.3 更新 `docs/release/release-setup.md`

当前文档第 39 行说 "Desktop releases do not include the Python backend"，但 Phase 8A-1 已添加 sidecar 打包。更新为准确描述两种模式：
- sidecar 模式：Tauri bundle 内含 Python 后端（通过 `build_sidecar.ps1` 构建）
- venv 模式：需要用户自行安装 Python

## Part 2：启动修错

### 2.1 冷启动验证

Codex 按自己写的 quickstart 文档从零走一遍（模拟全新环境）：

```bash
# 1. 后端
python -m venv .venv
.venv/Scripts/activate    # Windows
pip install -e .
storyforge3 serve --port 8000

# 2. 验证
curl http://localhost:8000/api/health
# 期望：{"status": "ok", ...}

# 3. 前端
cd web
pnpm install
pnpm dev
# 打开 http://localhost:5173
```

**遇到任何阻塞就修。** 包括但不限于：
- `ModuleNotFoundError`（缺少 hidden import 或 package data）
- 配置文件缺失导致启动崩溃
- CORS 问题
- 前端 API 调用 404
- 静态文件路径错误

### 2.2 端到端冒烟

启动后通过 Web UI 执行：

1. 创建一本测试书（都市/番茄/10 章/2500 字）
2. 构建世界观（种子："都市校园 + 超能力觉醒"）
3. 创建一个角色（"主角，18 岁，高中生，性格沉稳"）
4. Plan → Draft 第 1 章
5. Audit
6. Export

如果任何步骤报错，修代码直到跑通。

## Part 3：Dogfood 协议

### 3.1 创建 `docs/dogfood-protocol.md`

定义"真实写一章"的测试协议和问题记录模板：

```markdown
# Dogfood 测试协议

## 测试目标
用 StoryForge3 写《我是路人甲》的下一章真实内容，验证引擎在真实创作场景下的表现。

## 前置条件
- storyforge3 serve 运行中
- 《我是路人甲》书籍已创建（或有存量数据）
- AI 提供商已配置且连通

## 执行步骤
1. 打开 Web UI，进入《我是路人甲》
2. 选择下一个未写章节
3. 执行 plan → 记录：规划质量、目标清晰度、上下文完整性
4. 执行 draft → 记录：字数、耗时、文风一致性、角色区分度
5. 执行 audit → 记录：规则命中、误判率、阻断问题
6. 如需 revise → 记录：修订模式选择是否合理、修订效果
7. 执行 truth_extract → 记录：提取质量、遗漏、错误
8. 执行 export → 记录：格式正确性

## 记录模板

| 维度 | 评分(1-5) | 备注 |
|------|-----------|------|
| 启动流畅度 | | 遇到的阻塞 |
| 规划质量 | | plan 输出是否有用 |
| 草稿质量 | | 文风、角色、情节 |
| 审计准确度 | | 误判/漏判 |
| 修订效果 | | 修订后是否改善 |
| UI 操作体验 | | 别扭/困惑的地方 |
| LLM 成本 | | 大约 token 消耗 |
| 总体可用性 | | 能否替代手动流程 |

## 问题列表

| # | 严重度 | 问题描述 | 复现步骤 | 修复建议 |
|---|--------|---------|---------|---------|
| 1 | 阻断/严重/一般 | | | |
```

### 3.2 执行 Dogfood（如果环境允许）

如果 Codex 的环境有 LLM 提供商访问权限，执行一次真实 dogfood 并将结果填入协议模板。如果环境不支持 LLM 调用，只交付文档和协议模板。

## Part 4：借鉴来源

### 文档结构借鉴

| 借鉴内容 | 来源文件 | 借鉴方式 | 新写比例 |
|---------|---------|---------|---------|
| README "快速开始"章节结构 | `storyforge2/README.md` 第 19-35 行 | 骨架移植：复用 venv→install→test 结构，替换为 SF3 的命令和依赖 | 40% |
| 故障排查章节格式 | `storyforge3/docs/architecture/mcp-registration.md` 第 119-168 行 | 骨架移植：现象→处理→验证的三段式结构 | 30% |
| providers.json 格式参考 | `storyforge3/src/storyforge3/llm/ccswitch_reader.py` | 模式复用：从代码提取实际 JSON 结构 | 20% |

### 无直接来源说明

- `docs/quickstart.md` 的"从零到第一章"操作指南、环境变量说明、CC-Switch 配置步骤：**无现成来源**。这些是 SF3 特有的配置和流程，需要新写。
- `docs/dogfood-protocol.md` 的测试协议和记录模板：**无现成来源**。这是针对 SF3 管线设计的质量评估框架。
- 新写比例约 50-60%。原因：文档内容高度依赖 SF3 特有的配置模型（pydantic-settings）、CC-Switch 集成流程、Web UI 操作路径，无法从其他项目移植。

## 验收标准

### 文档检查

- [ ] `storyforge3/README.md` 存在，包含完整的快速开始章节
- [ ] `docs/quickstart.md` 存在，包含环境变量说明和故障排查
- [ ] `docs/dogfood-protocol.md` 存在，包含记录模板
- [ ] `docs/release/release-setup.md` 已更新，反映 sidecar 模式
- [ ] README 中的每条命令都是可复制粘贴执行的
- [ ] providers.json 示例是合法 JSON 且包含所有必需字段

### 启动验证

- [ ] 按照新写的 quickstart 文档，`storyforge3 serve` 能在全新 venv 中成功启动
- [ ] `http://localhost:8000/api/health` 返回 `{"status": "ok"}`
- [ ] `pnpm dev` 启动前端，`http://localhost:5173` 能打开并显示 UI
- [ ] 通过 Web UI 能创建书籍、构建世界观、创建角色
- [ ] 通过 Web UI 能执行 plan → draft → audit 管线（需 LLM 提供商）

### 质量门禁

- [ ] `pytest tests/ -q` 全绿，无退步（基线 468）
- [ ] `ruff check .` clean
- [ ] `pnpm test` 全绿（基线 62）
- [ ] `pnpm build` 通过
- [ ] 无新 `TODO` / `FIXME` 残留

### 文档更新

- [ ] `docs/history.md` 添加 Phase 8.5 条目，`docs/current.md` 更新当前基线
- [ ] `CLAUDE.md` 添加 Phase 8.5 完成记录

## 估算工作量

| 文件 | 估算行数 | 说明 |
|------|---------|------|
| `README.md` | ~120 行 | 新建 |
| `docs/quickstart.md` | ~200 行 | 新建 |
| `docs/dogfood-protocol.md` | ~80 行 | 新建 |
| `docs/release/release-setup.md` | 修改 ~10 行 | 更新 sidecar 描述 |
| 代码修错 | ≤50 行 | 冷启动发现的问题修复 |
| **合计** | **~460 行** | 以文档为主 |

## 不做的事（Out of Scope）

- ❌ 不加新功能
- ❌ 不做 Tauri 桌面端实机验证（需要 Rust 工具链，独立进行）
- ❌ 不做 PyInstaller 实际打包（独立进行）
- ❌ 不做性能优化
- ❌ 不做多语言文档（中文即可）
- ❌ 不做 API 文档自动生成（OpenAPI schema 已由 FastAPI 自动提供）
