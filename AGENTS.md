# StoryForge3 — Codex Instructions

> 本文件是 Codex 在 `storyforge3` 工作时的唯一权威指引。
> 如与 `目标.md` 冲突，以本文件为准。

## Project Identity

StoryForge3 是**中文网文全流程创作引擎**——从空白页到可发布章节。它不是 StoryForge2 的续修版本，
而是一个新项目，在 SF2 已验证能力（36 规则、Truth 管理、5 修订模式等）的基础上，
补上"从零创建小说"的能力，并通过 CCSwitch 双层路由和 Service Interface 为前后端分离做好准备。

核心判断原则：

- **完整创作流程**。从"新建一本书"开始，不依赖已有章节或手动准备的材料。
- **真实生产优先**。fallback、样例、合成数据、机械导入不算成功。
- **Fail closed**。LLM 调用失败、truth 提取失败、审计超时 → 停在人工复核，不许静默继续。
- **CCSwitch 只读导入 + Provider 直连**。SF3 只读 CCSwitch SQLite provider 配置，导入到 `.storyforge3/providers.json` 作为项目本地 provider profile，然后直接调 Provider API，不走请求代理中转。
- **服务层优先**。所有业务逻辑通过 Service Interface 暴露，前端只是 interface 的消费者。
- **人工确认优先**。approve、export、发布前的状态推进必须有明确的人类确认点。

## StoryForge2 的教训

StoryForge3 的设计直接来源于 StoryForge2 的失败模式。以下是已知的、
不得在 StoryForge3 中重复的错误：

| # | 错误 | 后果 | StoryForge3 对策 |
|---|------|------|------------------|
| 1 | 直接把 provider 密钥提交到仓库 | 密钥泄漏，P0 安全问题 | 只读 CCSwitch SQLite 导入 provider，本地 `.storyforge3/` 不入版本控制 |
| 2 | config/storyforge2.toml 有非法 TOML 语法 | 配置解析不靠谱，靠 local 优先才没炸 | 使用 pydantic-settings + .env，不做手写 TOML |
| 3 | provider_name 与 model_provider 字段混乱 | 切换不稳 | 只认一个字段：`model_id`，由 CCSwitch 路由 |
| 4 | truth extractor 失败后返回空数组继续 | 产生 truth gap 但系统假装正常 | fail closed：失败 = 停下来 |
| 5 | summary 掩盖 truth gap | 第 7 章"成功"但 8-10 的 gap 文件没进 summary | 结果层诚实暴露 gap |
| 6 | 396 tests 全过 ≠ 可用于生产 | 测试覆盖了引擎逻辑，没覆盖真实 LLM 调用 | eval-first：必须有真实 LLM 调用的回归样例 |

## Architecture

### AI 项目形态

StoryForge3 属于 **Agent 系统**（LLM 可调用工具或改变外部状态）。

必须具备：

- 工具 allowlist
- 单任务预算和超时
- 最大循环次数
- 外部写入前确认点
- kill switch

### 目录结构

遵循 `通用开发规范文件夹/02-项目脚手架模板.md` §2.1（本地工具）+ §2.7（AI/LLM 补充）：

```
storyforge3/
├── src/
│   └── storyforge3/
│       ├── __init__.py              # 公开 API
│       ├── __main__.py              # CLI 入口
│       ├── config.py                # pydantic-settings 配置（含按任务模型路由）
│       ├── models.py                # 全部数据模型（frozen dataclass）
│       ├── workflow.py              # 章节管线编排
│       ├── llm/                     # LLM 集成（只接 CCSwitch）
│       │   ├── __init__.py
│       │   ├── client.py            # CCSwitch 配置直读 + Provider 直连客户端（支持 per-request model）
│       │   └── protocol.py          # 请求/响应协议定义
│       ├── services/                # ★ 服务层接口（前后端边界）
│       │   ├── __init__.py
│       │   ├── protocols.py         # 全部 Service Protocol 定义
│       │   ├── book_service.py      # 书籍管理实现
│       │   ├── world_service.py     # 世界构建实现
│       │   ├── character_service.py # 角色管理实现
│       │   ├── volume_service.py    # 卷纲规划实现
│       │   └── chapter_service.py   # 章节生命周期实现
│       ├── audit/                   # 质量审计
│       │   ├── __init__.py
│       │   ├── rules.py             # 36 机械规则（从 SF2 迁移）
│       │   ├── runner.py            # 审计执行器
│       │   ├── context.py           # MechanicalContext 构建
│       │   ├── chinese_text.py      # 中文文本工具函数
│       │   └── thresholds.py        # 规则阈值常量
│       ├── truth/                   # Truth 管理（fail closed）
│       │   ├── __init__.py
│       │   ├── extractor.py         # Truth 提取
│       │   ├── database.py          # SQLite truth_entries
│       │   ├── retriever.py         # relevance 检索
│       │   └── store.py             # JSON + SQLite 双写
│       ├── export/                  # 平台导出
│       │   ├── __init__.py
│       │   ├── formatter.py         # 番茄小说 TXT
│       │   ├── markdown.py          # Markdown 合集
│       │   ├── epub_format.py       # EPUB
│       │   └── qidian.py            # 起点 TXT
│       ├── prompts/                 # Prompt 版本管理
│       │   ├── __init__.py
│       │   └── registry.py          # 版本化 Prompt 注册表
│       └── state/                   # 章节状态管理
│           ├── __init__.py
│           └── machine.py           # 状态机
├── tests/
│   ├── conftest.py
│   └── test_<concern>.py
├── evals/                           # AI 功能回归样例
│   └── <scenario>/
├── docs/
│   └── adr/
├── prompts/                         # 生产 Prompt 模板
│   ├── system/
│   ├── tasks/
│   └── CHANGELOG.md
├── .env.example                     # 环境变量示例（无真实密钥）
├── .gitignore
├── pyproject.toml
├── AGENTS.md                        # 本文件
├── CLAUDE.md                        # AI 协作上下文
├── README.md
└── 目标.md                          # 产品目标
```

### 代码规模控制

来自 `通用开发规范文件夹/05-质量门禁与检查清单.md` §VII，
原文为"指标 → 阈值 → 超过时的行动"三列结构，阈值是信号灯不是护栏：

| 指标 | 参考线 | 超过时的行动 |
|------|--------|-------------|
| 单文件行数 | 以功能边界为准 | 职责混杂或明显臃肿时拆分 |
| 单函数行数 | ~50 行 | 拆分子函数 |
| 嵌套深度 | ~3 层 | early return 平铺 |
| 函数参数 | ~4 个 | 改用对象 / dataclass |
| 圈复杂度 | ~10 | 拆分分支逻辑 |
| 单类方法数 | ~15 | 拆分职责 / 提取协作者 |
| 模块直接依赖 | ~8 | 引入门面模块 / 调整边界 |

规范优先级（冲突时按此顺序裁决）：
安全 > 架构 > 类型安全 > 规模控制 > 命名 > 风格 > Git > 测试 > 文档

## CCSwitch Integration

### 架构：只读导入 + 直连 Provider

SF3 不通过 CCSwitch 请求代理，而是只读 CCSwitch SQLite provider 配置，导入到 StoryForge3 项目本地配置后自己调 Provider API：

```
CCSwitch provider database
     │
     ▼ 只读
SF3 ──→ CCSwitchDBReader
     │
     ▼ import selected providers
.storyforge3/providers.json（项目本地，gitignored）
     │
     ├── provider: Codex 直连中转
     ├── base_url: https://api.vip1129.cc
     ├── api_key: <local imported secret>
     └── model: gpt-5.5
          │
          ▼
    LLMService 直接 POST {base_url}/v1/responses
```

**为什么不用代理**：CCSwitch 在这里是 provider 配置源，不是请求中转站。SF3 导入配置后直连 provider，减少一层网络跳转和运行时依赖。

### 按任务模型路由

SF3 可为不同任务指定不同模型（空值 = 用 active provider 的默认模型）：

```env
DEFAULT_MODEL=gpt-4o       # 回退模型
WRITER_MODEL=              # 空 → 用 default_model
AUDITOR_MODEL=gpt-4o       # 高精度
TRUTH_EXTRACTOR_MODEL=     # 空 → 用 default_model
ARCHITECT_MODEL=           # 空 → 用 default_model
PLANNER_MODEL=             # 空 → 用 default_model
```

Service 层通过 `config.model_for_task("writer")` 解析，传给 LLMService 的 `model` 参数。

### 接入边界

**CCSwitchDBReader（llm/ccswitch_db_reader.py）**：
- 只读 CCSwitch 的 `cc-switch.db` provider 配置
- 不写不改 CCSwitch 的任何数据
- 读不到配置时返回空列表或 None

**ProviderConfigManager（llm/provider_config.py）**：
- 将用户选择的 CCSwitch provider 导入 `.storyforge3/providers.json`
- 本地 provider profile 可记录验证状态、端点格式、模型信息
- `.storyforge3/` 必须保持 gitignored

**LLMService（llm/llm_service.py）**：
- 用 active provider profile 拿到 base_url / api_key / model
- 直接调 Provider 的 OpenAI Responses / OpenAI Chat / Anthropic / Gemini 端点
- OpenAI-compatible provider 不跨协议族 fallback 到 Anthropic

**禁止**：
- 写入 CCSwitch 的数据库或配置文件
- 依赖 CCSwitch 请求代理运行
- 将 `.storyforge3/providers.json`、真实 API key、运行书稿或 E2E 日志提交到仓库

**允许**：
- 只读 CCSwitch SQLite
- 将 provider 导入 StoryForge3 本地 `.storyforge3/providers.json`
- 在日志中记录 provider/model/usage 信息

### 错误处理

LLM 调用失败的策略：

| 错误类型 | 处理 |
|----------|------|
| CCSwitch 不可达 | 报错停止，提示用户启动 CCSwitch |
| 429 Rate Limit | 等待重试（最多 3 次，指数退避），仍失败则停止 |
| 5xx Provider Error | 记录错误并停止；可在 CCSwitch GUI 切换 provider 后重跑 |
| 超时 | 记录日志，标记章节需人工复核 |
| 响应格式错误 | 标记失败，不尝试猜测或修复 |

**禁止**：失败后自动生成占位内容、空 truth、合成数据继续流程。

## Truth Management

### Fail Closed 原则

Truth 提取是 StoryForge3 最关键的安全边界。

```python
# StoryForge2 的错误做法（禁止）：
if extraction_failed:
    return {"fact_assertions": [], "notes": ["extraction_failed"]}  # 假装成功

# StoryForge3 的正确做法：
if extraction_failed:
    raise TruthExtractionError(
        chapter=chapter_no,
        reason=error_detail,
        action_required="human_review"
    )
```

规则：

1. Truth 提取失败 → 章节状态变为 `needs_review`，不自动推进。
2. Truth gap（某章缺 truth）→ 在后续章节的结果中**明确标注**，不许用 summary 掩盖。
3. 不允许生成合成 truth（synthetic truth）来填补 gap。
4. 所有 truth 记录必须标记来源：`runtime_native` 或 `manual_recovery`。
5. `manual_recovery` 的 truth 不覆盖 `runtime_native` 的 truth。

### Truth 生命周期

```
chapter_written → truth_extract(必须成功) → truth_commit → truth_snapshot_for_next
                                              ↓ 失败
                                        needs_review (人工)
```

## Chapter Pipeline

### 完整创作管线

```
create_book → build_world → create_characters → plan_volumes →
[单章循环] plan_chapter → compose → draft → settle → audit → revise → approve → export → state_update
```

### 管线阶段定义

| 阶段 | 输入 | 输出 | 实现服务 |
|------|------|------|----------|
| create_book | 书名、类型、平台、目标 | BookMeta | BookService |
| build_world | 类型 + 创意种子 | WorldConfig | WorldService |
| create_characters | 世界观 + 卷纲 | Character[] + Relationship[] | CharacterService |
| plan_volumes | 书籍参数 + 世界观 | VolumeOutline[] | VolumeService |
| plan_chapter | 上下文 + 上一章 truth | ChapterIntent | ChapterService |
| compose | 意图 + 规则栈 | 上下文包 | ChapterService |
| draft | 上下文包 | 章节文本 | ChapterService |
| settle | 章节文本 | TruthData | TruthService |
| audit | 章节文本 | AuditResult | AuditService |
| revise | 审计结果 + 文本 | 修订文本 | ChapterService |
| approve | 审计通过 + 文本 | ChapterResult | ChapterService |
| export | approved 章节 | TXT / MD | ExportService |
| state_update | export 结果 | 新 truth + 状态 | TruthService + StateMachine |

### 单章核心管线（继承自 SF2，已验证）

```
plan → compose → draft → settle → audit → revise → approve → export → state_update
```

每个阶段的失败策略：

| 阶段 | 失败策略 |
|------|----------|
| plan | LLM 失败 → 停止 |
| draft | LLM 失败 → 停止 |
| settle | Truth 提取失败 → needs_review（人工） |
| audit | blocking → revise + re-audit 循环（最多 2 轮）；超过上限进入 needs_review |
| approve | 人工决定 |
| export | 格式错误 → 报错 |
| state_update | truth 失败 → needs_review |

### 已补齐的阶段

以下能力已从后置迁移补齐到当前核心引擎：

- Blocking audit 修订闭环：最多 2 轮 revise → re-audit，失败返回 `revision_exhausted` / `needs_review`。
- 角色与世界上下文注入：draft/revise payload 包含 world_config、characters、relevant truth，降低角色漂移。
- SQLite 记忆数据库：TruthStore JSON 备份 + SQLite relevance 检索，prompt truth 默认限制 4000 字。
- 多章节连续生产：当前 `Codex 直连中转` provider 已完成真实 3 章 E2E，`3/3 exported`，SQLite truth 可跨章召回。
- 多格式导出：番茄 TXT、Markdown 合集、EPUB、起点 TXT。
- Daemon 核心：批量章节、目标章数、单轮上限、连续失败暂停；通知渠道/定时入口仍后置。

## Service Interface

### 设计原则

所有业务能力封装为 async Service，前端（CLI / Web / Desktop）只通过 Service Protocol 交互：

```
前端 (CLI/Web/Desktop)
     │
     ▼
Service Protocols (services/protocols.py)
     │
     ▼
Concrete Services (services/book_service.py 等)
     │
     ├──→ LLM (CCSwitch Client)
     ├──→ Storage (JSON 文件)
     └──→ Audit / Truth / State
```

未来前端实现时，只需加一层 HTTP/WebSocket 适配器，Service 层无需改动。

### Service 清单

| 服务 | 职责 |
|------|------|
| LLMService | Provider profile 直连 + 多协议路由/重试 + 按任务模型路由 |
| BookService | 书籍创建/查询/状态管理 |
| WorldService | 世界构建/规则管理 |
| CharacterService | 角色创建/关系/弧线管理 |
| VolumeService | 卷纲规划/章节分配 |
| ChapterService | 章节全生命周期 |
| AuditService | 36 机械规则 + LLM 审计 |
| TruthService | Truth 提取/存储/查询（fail-closed） |
| ExportService | 番茄 TXT / Markdown / EPUB / 起点 TXT 导出 |
| DaemonService | 批量章节生产核心逻辑 |
| PromptService | Prompt 模板管理 |
| StyleService | 风格契约管理 |

接口定义在 `src/storyforge3/services/protocols.py`，实现类在各自模块。

## Quality Audit

### 从 StoryForge2 迁移的规则

迁移 36 条机械规则的核心逻辑，但重写为 StoryForge3 的接口：

- **ai_tell** (10 rules): report term leak, meta narration, AI slop
- **style** (10 rules): hedge words, template emotion, show-don't-tell
- **structure** (7 rules): action ratio, pacing, info dump, hook
- **meta** (7 rules): forbidden tokens, output leak, engine term leak

规则判定分三级：

- **blocking**: 必须修复才能继续
- **warning**: 建议修复，人工可选择跳过
- **info**: 纯信息，不影响流程

### 审计结果格式

```python
@dataclass(frozen=True)
class AuditResult:
    chapter_no: int
    passed: bool
    blocking_issues: tuple[str, ...]   # 必须修
    warnings: tuple[str, ...]          # 建议修
    info: tuple[str, ...]              # 参考
    rule_results: tuple[RuleResult, ...]
```

## Prompt Management

### 版本化要求

来自 `通用开发规范文件夹/06-AI产品专项规范.md` §II：

- 每个 Prompt 必须记录：版本号、用途、输入契约、输出契约、最后修改日期
- 模型版本不使用 `latest`；升级模型必须经过 eval 验证
- Prompt 变更必须可回滚
- Prompt 存放在 `prompts/` 目录，有 `CHANGELOG.md`

### Prompt 注册表

```python
# prompts/registry.py
class PromptRegistry:
    def get(self, name: str, version: str | None = None) -> PromptTemplate
    def register(self, name: str, template: PromptTemplate) -> None
    def list_versions(self, name: str) -> list[str]
```

## Security

### 硬性规则

1. **无硬编码密钥**。真实 API key 只能存在于本地 `.storyforge3/` 或用户环境中，不能入 git。
2. **.env.example 不含真实值**。只有变量名和注释说明。
3. **profiles/ 不入版本控制**。如果存在 per-book 配置，放在 `.gitignore` 管控的目录。
4. **日志脱敏**。LLM 调用日志不记录完整 prompt（可能含敏感内容），只记录 metadata。
5. **外部写入需确认**。export、发布等改变外部状态的操作必须有人类确认点。

### .gitignore 必须包含

```
__pycache__/
*.pyc
*.pyo
*.db
*.tmp
*.bak
*.log
.env
.vscode/
.idea/
books/
.DS_Store
Thumbs.db
```

## Migration from StoryForge2

### 已迁移并适配的资产

这些模块的核心逻辑已经端口到 StoryForge3 当前接口：

| 资产 | 来源 | 迁移方式 |
|------|------|----------|
| 36 条机械规则 | `engine/services/gate_runner.py` | 提取规则逻辑，重写接口层 |
| standalone_audit 思路 | `scripts/standalone_audit.py` | 重写为 CLI 子命令 |
| Prompt Registry | `engine/prompts/registry.py` | 适配新接口 |
| Platform Formatter | `engine/services/platform_formatter.py` | 番茄 TXT + MD + EPUB + 起点 TXT |
| Revision Mode 推荐 | `engine/services/revision_mode_recommender.py` | 适配新接口 |

### 已重写的资产

| 资产 | 原因 |
|------|------|
| LLM Provider 全部 | 改为 CCSwitch 配置直读 + Provider 直连客户端 |
| Truth Extractor | 必须改为 fail-closed |
| Config 加载 | 改为 pydantic-settings + .env |
| State Machine | 简化为 MVP 状态集 |
| Result Layer | 重新设计，诚实暴露 gap |

### 仍后置的资产

| 资产 | 原因 |
|------|------|
| Studio TUI | CLI 先行 |
| Web Studio | FastAPI REST/SSE 已准备，前端尚未实现 |
| P5 通知/调度 | Daemon 核心已完成，外部通知渠道依赖配置 |

## First Acceptance Goal

用《我是路人甲》完成从零创建到第 3 章的完整验证：

- [ ] **创建书籍**：书名、类型（都市玄幻）、平台（番茄小说）、目标字数
- [ ] **世界构建**：存在感系统、检测中心、异常等级体系
- [ ] **角色设计**：林默（主角）+ 3 个核心配角 + 关系
- [ ] **卷纲规划**：第一卷 10 章结构 + 关键场景
- [ ] **CCSwitch**：全局 + 按任务路由正常工作
- [ ] **章节生产**：前 3 章通过完整管线（plan → draft → audit → approve → export）
- [ ] **Truth**：无 gap，3 章状态连续
- [ ] **导出**：番茄小说 TXT 格式正确
- [ ] **Service Interface**：所有操作通过 Protocol 接口完成，无直接存储访问

## Execution Rules

### 通用

- 代码质量优先于开发速度。
- 并行子代理只在独立模块之间使用。
- 不要盲目信任子代理的输出，本地审查后才能采纳。
- 所有测试必须可复跑，不允许依赖外部服务的测试挂了就跳过。

### 命名

- 目录：`kebab-case` 或 `lowercase`
- 常量：`UPPER_SNAKE_CASE`
- 布尔：`is`/`has`/`can`/`should` 前缀
- 类/类型：`PascalCase`
- 函数：动词开头
- 测试文件：`test_<name>.py`
- 分支：`type/kebab-case`（`feature/truth-extractor`）
- Commit：Conventional Commits（`feat:`, `fix:`, `refactor:`）

### 错误处理

- 禁止空 catch 块
- 错误消息必须包含诊断上下文
- 不信任外部数据（API 响应、用户输入、文件内容）
- 在系统边界验证，fail fast

### 注释

- 解释 WHY 和业务上下文
- 不翻译代码本身
- 复杂算法、特殊业务逻辑、临时兼容 hack 必须注释

## Non-Goals

除非用户明确要求，不做：

- Web Studio / 前端 UI（先定义好接口，后续实现）
- 富文本编辑器
- 通用写作 IDE
- 英文扩展
- LoRA / fine-tuning
- 复杂角色卡片 UI
- 写入或修改 CCSwitch SQLite（只读导入 provider 允许）
- truth fallback 自动提交
- 无人值守 approve/export
- 同人小说/短篇管线（后续扩展）
- Daemon 通知渠道和定时调度入口（核心 run_batch 已完成）

## Testing

### 单元测试

- 框架：pytest 或 unittest
- 当前实时基线见 `docs/current.md`；Phase 10A-1 记录为 498 passed、91% coverage，`ruff check .` clean
- 覆盖率目标：≥ 90%
- 外部依赖（CCSwitch）用 mock，不依赖真实 LLM 调用

### Eval 样例

来自 `通用开发规范文件夹/06-AI产品专项规范.md` §III：

每个 AI 功能至少准备：

- 正常样例：主路径输入
- 边界样例：空输入、超长、格式异常
- 恶意样例：prompt injection、越权
- 回归样例：历史问题、用户纠错

### CCSwitch 集成验证

真实 LLM 验证使用当前 CCSwitch provider 配置：

- Provider 示例：`Codex 直连中转`
- Base URL：`https://api.vip1129.cc/v1`
- Model：`gpt-5.5`
- Smoke：`scripts/test_real_llm.py`
- 单章 E2E：`scripts/e2e_test.py`
- 多章节 E2E：`scripts/e2e_multi_chapter.py`
- API 服务：`storyforge3 serve`

当前 `Codex 直连中转` provider 已通过 smoke、单章 E2E 和 3 章多章节 E2E。最新通过 run：
`books/e2e-multi-20260608-180847`，结果为 `success=True`、`exported_chapters=3`、`failed_chapters=0`，
并通过跨章 truth 检索验证。

如果 smoke 通过但完整 E2E 失败，先区分 provider 侧 5xx/504、超时、响应格式错误和 SF3 代码缺陷；不要把 provider 失败记录为引擎通过。

## Key References

| 文档 | 说明 |
|------|------|
| `目标.md` | 产品目标定义（本文件优先级更高时以本文件为准） |
| `通用开发规范文件夹/` | 开发规范（目录结构、质量门禁、AI 专项） |
| `cc-switch-main/` | CCSwitch 源码（不直接依赖，只了解接口） |
| `storyforge2/` | StoryForge2 源码（迁移来源，不改它） |
| `storyforge2/docs/合约文档/` | StoryForge2 合约文档（术语参考） |

## Communication Rules

- 具体优先，证据优先。引用文件路径、命令输出、artifact ID。
- 区分"已检查"、"已本地修改"、"已本地验证"、"已提交"。
- 如果结果是部分的、回填的、模拟的或历史的，明确说明。
- 不确定就说"我不确定"，不编造。
