# Codex 指令：Phase 6B-1 — 短篇管线后端（模型 + Service + API）

> 发出日期：2026-06-09
> 产品经理：Claude Code PM
> 执行者：Codex
> 前置条件：Phase 6C 完成（358 后端 tests, 34 前端 tests, ruff clean）

---

## 任务概述

为 StoryForge3 添加短篇创作管线。短篇是 5000-20000 字的单篇作品，区别于现有的多章节长篇管线。

**核心区别**：

| 维度 | 长篇（现有） | 短篇（本阶段） |
|------|------------|--------------|
| 结构 | 卷 → 多章 → 每章 2000-3000 字 | 单篇 → 5000-20000 字 |
| 规划 | VolumeOutline + ChapterIntent × N | 单个 ShortStoryPlan |
| 管线 | plan → draft → normalize → audit → revise → approve → truth → export（8步） | plan → draft → audit → revise → export（5步） |
| 真相系统 | 跨章 truth + SQLite | **不需要**（单篇无连续性） |
| 长度控制 | normalize 精确调整 | **不需要**（短篇字数更灵活） |
| 角色弧线 | 跨章追踪 | 单篇内自洽即可 |
| 导出 | 按章节分别导出 | 单文件导出 |

**核心原则**：短篇复用现有的 LLM 基础设施（LLMService + AuditRunner + PromptRegistry）和存储层（BookStorage），但数据模型和管线流程独立于长篇。不修改任何现有长篇代码。

---

## 数据模型

### 新增（`models.py`）

```python
class ShortStoryStatus(str, Enum):
    """短篇生命周期状态。"""
    EMPTY = "empty"
    PLANNED = "planned"
    DRAFTED = "drafted"
    AUDITED = "audited"
    REVISED = "revised"
    EXPORTED = "exported"

@dataclass(frozen=True)
class ShortStoryConfig:
    """短篇创建参数。"""
    title: str
    genre: str
    target_chars: int = 10_000  # 目标字数，默认 10000
    premise: str = ""           # 核心设定/一句话简介
    style: str = ""             # 风格要求（可选）

@dataclass(frozen=True)
class ShortStoryMeta:
    """短篇元数据。"""
    book_id: str
    title: str
    genre: str
    status: ShortStoryStatus
    target_chars: int
    premise: str
    style: str
    actual_chars: int = 0
    created_at: str = ""
    updated_at: str = ""

@dataclass(frozen=True)
class ShortStoryPlan:
    """短篇规划（替代长篇的 ChapterIntent + VolumeOutline）。"""
    book_id: str
    premise: str                # 核心设定
    opening: str = ""           # 开篇设计
    climax: str = ""            # 高潮设计
    ending: str = ""            # 结尾设计
    characters: str = ""        # 角色简述（非结构化，自然语言）
    key_scenes: tuple[str, ...] = ()  # 关键场景列表
    must_keep: tuple[str, ...] = ()   # 必须保留
    must_avoid: tuple[str, ...] = ()  # 必须避免

@dataclass(frozen=True)
class ShortStoryResult:
    """短篇管线结果。"""
    book_id: str
    status: ShortStoryStatus
    text: str
    audit: AuditResult | None = None
    error: str | None = None
```

### 不修改的现有模型

- `BookConfig` / `BookMeta` / `ChapterIntent` / `VolumeOutline` / `Character` / `WorldConfig` — 完全不动
- `AuditResult` / `RuleResult` — 短篇直接复用（36 条机械规则 + LLM 审计对短篇同样适用）

### 存储

```
books/{id}/
├── short_story.json      # ShortStoryMeta
├── short_plan.json       # ShortStoryPlan
├── short_text.md         # 短篇正文
└── exports/
    └── short.{format}    # 导出文件
```

**关键**：短篇复用现有的 `books/` 目录结构（同一个 book_id 空间），但数据文件名不同，与长篇文件互不干扰。

---

## 短篇管线流程

```
plan → draft → audit → revise (max 1) → export

5 步，对比长篇的 8 步：
  ✅ 保留：plan, draft, audit, revise, export
  ❌ 去掉：normalize（短篇字数灵活）, approve（短篇跳过人工确认，直接可导出）, truth_extract（单篇无连续性）
```

### 管线对比详解

| 步骤 | 长篇 | 短篇 | 差异说明 |
|------|------|------|---------|
| plan | `ChapterService.plan()` → ChapterIntent | `ShortStoryService.plan()` → ShortStoryPlan | 短篇规划不需要 outline_node/arc_context，改为 opening/climax/ending |
| draft | `ChapterService.draft()` → 2000-3000字/章 | `ShortStoryService.draft()` → 5000-20000字全文 | 短篇一次性生成全文，可能触发 chunked generation |
| normalize | `LengthNormalizer` 精确调整 | **跳过** | 短篇字数容忍度更高 |
| audit | 36机械规则 + LLM 4维度 | 36机械规则 + LLM 4维度 | **完全复用**，无需新写 |
| revise | 5种模式，最多2轮 | `patch` 模式，最多1轮 | 短篇只做局部修补，不做全量重写 |
| approve | 人工确认 | **跳过** | 短篇默认可导出 |
| truth | TruthExtractor → SQLite | **跳过** | 单篇无连续性 |
| export | 按章节分别导出 | 单文件导出 | 复用 PlatformFormatter，输出整个短篇 |

---

## 功能 1：ShortStoryService

### 新增文件

#### 1.1 `src/storyforge3/services/short_story_service.py`（新建，~200 行）

```python
class ShortStoryService:
    """短篇创作管线：plan → draft → audit → revise → export"""

    def __init__(
        self,
        config: StoryForge3Config,
        *,
        llm: Any | None = None,
        storage: BookStorage | None = None,
        paths: StoragePaths | None = None,
        audit_runner: AuditRunner | None = None,
        prompt_registry: PromptRegistry | None = None,
    ) -> None:
        # 与 ChapterService 相同的依赖注入模式
        ...

    async def create(self, config: ShortStoryConfig) -> ShortStoryMeta:
        """创建短篇书籍。"""
        ...

    async def plan(self, book_id: str) -> ShortStoryPlan:
        """规划短篇：opening/climax/ending + characters + key_scenes。
        
        LLM 调用：使用 'short_plan' prompt 模板。
        复用 PromptRegistry 的注册模式。
        """
        ...

    async def draft(self, book_id: str) -> str:
        """生成短篇全文。
        
        关键：短篇可能 5000-20000 字，需要处理大文本生成。
        - target_chars <= 8000：一次性生成
        - target_chars > 8000：使用 ChunkedGenerator 分段生成
        """
        ...

    async def audit(self, book_id: str) -> AuditResult:
        """审计短篇。完全复用现有 AuditRunner + LLM 审计。"""
        ...

    async def revise(self, book_id: str) -> ShortStoryResult:
        """修订短篇。固定使用 patch 模式，最多 1 轮。"""
        ...

    async def export(self, book_id: str, fmt: str = "tomato_txt") -> Path:
        """导出短篇为单文件。复用 PlatformFormatter。"""
        ...

    async def run_full_pipeline(self, book_id: str) -> ShortStoryResult:
        """一键运行完整短篇管线：plan → draft → audit → revise(if needed) → export"""
        ...

    def get_status(self, book_id: str) -> ShortStoryResult | None:
        ...

    def _save_text(self, book_id: str, text: str) -> None:
        """保存短篇正文到 short_text.md"""
        ...
```

**重要实现细节**：

1. **draft() 的分段生成**：当 `target_chars > 8000` 时，使用已有的 `ChunkedGenerator`（从 `llm/chunked_generator.py` 导入），与长篇 draft 相同的分段策略
2. **plan() 的 prompt 模板**：需要注册一个新的 `short_plan` prompt 到 PromptRegistry。模板内容参考 InkOS 的短篇规划逻辑，但简化为适合单篇的结构
3. **revise()**：固定使用 `patch` 模式（`revision_modes.py` 中的 `RevisionMode.PATCH`），最多 1 轮修订
4. **audit()**：直接调用 `AuditRunner.run()`（36 条机械规则）和 `LLMAuditor.audit()`（LLM 4 维度），零新代码
5. **export()**：调用 `PlatformFormatter.format_chapter()`（短篇视为"第1章"即可），输出到 `exports/short.{fmt}`

### Service Protocol

#### 1.2 `src/storyforge3/services/protocols.py` — 新增

```python
class ShortStoryServiceProtocol(Protocol):
    """Short story creation pipeline."""

    async def create(self, config: ShortStoryConfig) -> ShortStoryMeta: ...

    async def plan(self, book_id: str) -> ShortStoryPlan: ...

    async def draft(self, book_id: str) -> str: ...

    async def audit(self, book_id: str) -> AuditResult: ...

    async def revise(self, book_id: str) -> ShortStoryResult: ...

    async def export(self, book_id: str, fmt: str = "tomato_txt") -> Path: ...

    async def run_full_pipeline(self, book_id: str) -> ShortStoryResult: ...

    def get_status(self, book_id: str) -> ShortStoryResult | None: ...
```

---

## 功能 2：API 路由

#### 2.1 `src/storyforge3/api/routes/short_story.py`（新建，~100 行）

```python
router = APIRouter(prefix="/api/short-stories", tags=["short-stories"])

class CreateShortStoryRequest(BaseModel):
    title: str
    genre: str
    target_chars: int = 10_000
    premise: str = ""
    style: str = ""

@router.post("")
async def create_short_story(req: CreateShortStoryRequest, ...): ...

@router.get("/{book_id}")
async def get_short_story(book_id: str, ...): ...

@router.post("/{book_id}/plan")
async def plan_short_story(book_id: str, ...): ...

@router.post("/{book_id}/draft")
async def draft_short_story(book_id: str, ...): ...

@router.post("/{book_id}/audit")
async def audit_short_story(book_id: str, ...): ...

@router.post("/{book_id}/revise")
async def revise_short_story(book_id: str, ...): ...

@router.post("/{book_id}/export")
async def export_short_story(book_id: str, fmt: str = "tomato_txt", ...): ...

@router.post("/{book_id}/run")
async def run_full_pipeline(book_id: str, ...): ...
```

**注意路由前缀**：用 `/api/short-stories` 而不是 `/api/books/{id}/short`。短篇是独立的资源类型，不挂在 books 下面。

#### 2.2 `src/storyforge3/api/app.py` — 注册路由

添加 `short_story` 路由。

#### 2.3 `src/storyforge3/api/deps.py` — 注入依赖

添加 `get_short_story_service()` 依赖注入函数。

---

## 功能 3：Prompt 模板

#### 3.1 注册 `short_plan` prompt

在 `src/storyforge3/prompts/registry.py` 的 `create_default_registry()` 中添加：

```python
registry.register("short_plan", "v1", SHORT_PLAN_SYSTEM_PROMPT)
```

`SHORT_PLAN_SYSTEM_PROMPT` 内容（新写，但借鉴 InkOS 的短篇规划逻辑）：

```
你是一个专业的短篇小说规划师。根据用户提供的设定，为短篇小说设计完整的故事框架。

你需要输出以下结构：

## 核心设定
（复述并扩展用户提供的 premise）

## 开篇设计
- 第一段如何抓住读者
- 开篇场景的具体画面
- 主角登场方式

## 高潮设计
- 核心冲突是什么
- 冲突如何升级
- 转折点在哪里

## 结尾设计
- 如何收束情节
- 情感落点是什么
- 是否留悬念

## 角色
简要描述 2-4 个关键角色的核心特征和互动关系。

## 关键场景
列出 3-6 个关键场景，每个场景一句话描述。

## 写作约束
- 必须保留：[从用户 premise 推断]
- 必须避免：[常见的短篇小说败笔]

输出字数目标：{target_chars} 字
```

#### 3.2 注册 `short_draft` prompt

```python
registry.register("short_draft", "v1", SHORT_DRAFT_SYSTEM_PROMPT)
```

```
你是一个专业的中文短篇小说作者。根据提供的短篇小说规划，写一篇完整的短篇小说。

写作要求：
1. 字数目标：{target_chars} 字（中文字符）
2. 一次性输出完整故事，不要分段
3. 严格遵循规划中的开篇、高潮、结尾设计
4. 每个关键场景都要出现
5. 角色对话要有辨识度，符合角色性格
6. 避免以下 AI 常见问题：
   - 不要用"他感到"、"他意识到"、"他明白了"等内心独白标记词
   - 不要用"总的来说"、"综上所述"等总结性语言
   - 不要用"心中一震"、"恍然大悟"等陈旧表达
   - 用动作、表情、环境替代直白的情绪描述
7. 叙事节奏：开篇有画面感，中段有张力，结尾有余韵
```

---

## 文件改动清单

### 后端新增（~400 行）

| 文件 | 操作 | 行数 | 说明 |
|------|------|------|------|
| `src/storyforge3/models.py` | 修改 | +45 | ShortStoryStatus + ShortStoryConfig + ShortStoryMeta + ShortStoryPlan + ShortStoryResult |
| `src/storyforge3/services/short_story_service.py` | 新建 | +200 | 短篇管线服务 |
| `src/storyforge3/services/protocols.py` | 修改 | +12 | ShortStoryServiceProtocol |
| `src/storyforge3/services/deps.py` | 修改 | +5 | get_short_story_service() |
| `src/storyforge3/api/routes/short_story.py` | 新建 | +100 | 8 个 API 端点 |
| `src/storyforge3/api/app.py` | 修改 | +2 | 注册路由 |
| `src/storyforge3/prompts/registry.py` | 修改 | +20 | 注册 short_plan + short_draft prompt |

### 后端测试新增（~150 行）

| 文件 | 说明 |
|------|------|
| `tests/test_short_story_service.py` | 短篇管线核心测试（~80 行） |
| `tests/api/test_short_story.py` | API 端点集成测试（~50 行） |

---

## 复用清单

| 组件 | 来源 | 复用方式 |
|------|------|---------|
| `AuditRunner` | `audit/runner.py` | 直接调用 `run()` 方法 |
| `LLMAuditor` | `audit/llm_auditor.py` | 直接调用 `audit()` 方法 |
| `ChunkedGenerator` | `llm/chunked_generator.py` | draft() 超过 8000 字时分段生成 |
| `PlatformFormatter` | `export/formatter.py` | 导出时格式化 |
| `BookStorage` | `storage.py` | 读写 books/{id}/ 下的文件 |
| `StoragePaths` | `storage.py` | 路径管理 |
| `PromptRegistry` | `prompts/registry.py` | 注册和获取 prompt 模板 |
| `LLMService` | `llm/` | 生成文本 |
| `RevisionModeRecommender` | `audit/revision_modes.py` | 短篇固定用 PATCH 模式 |
| `PipelineLogger` | `logging/pipeline_logger.py` | JSONL 日志（可选） |

**不修改的现有文件**（除 models.py/protocols.py/deps.py/app.py/registry.py 的小幅扩展外）：
- `chapter_service.py` — 不动
- `book_service.py` — 不动
- `export_service.py` — 不动（短篇用 PlatformFormatter 但不用 ExportService 的按章逻辑）

---

## 测试

### 后端

```powershell
cd storyforge3
.\.venv\Scripts\python.exe -m pytest tests/ -q   # 358+ tests 不退步
ruff check .
```

新增测试要点：

1. **`test_short_story_service.py`**：
   - `test_create_short_story_saves_meta` — 创建短篇保存 short_story.json
   - `test_plan_generates_short_plan` — plan() 调用 LLM 并返回 ShortStoryPlan
   - `test_draft_generates_full_text` — draft() 生成短篇正文
   - `test_draft_uses_chunked_for_long_stories` — target_chars > 8000 时使用 ChunkedGenerator
   - `test_audit_reuses_existing_rules` — audit() 复用 36 条规则
   - `test_revise_uses_patch_mode_max_one_round` — 修订固定 patch + 1 轮
   - `test_export_single_file` — 导出为单文件
   - `test_run_full_pipeline_end_to_end` — 全流程测试
   - `test_get_status_returns_none_for_unknown` — 不存在的短篇返回 None

2. **`tests/api/test_short_story.py`**：
   - `test_create_short_story_201` — 创建短篇成功
   - `test_plan_short_story_200` — 规划成功
   - `test_run_full_pipeline_200` — 一键运行成功
   - `test_get_short_story_404` — 不存在时 404

---

## 验收标准

### 数据模型

- [ ] ShortStoryStatus 有 6 个状态（EMPTY/PLANNED/DRAFTED/AUDITED/REVISED/EXPORTED）
- [ ] ShortStoryConfig 包含 title/genre/target_chars/premise/style
- [ ] ShortStoryPlan 包含 premise/opening/climax/ending/characters/key_scenes
- [ ] 现有模型（BookConfig/BookMeta/ChapterIntent/VolumeOutline）零改动

### 短篇管线

- [ ] plan() 生成包含开篇/高潮/结尾设计的完整规划
- [ ] draft() 生成 5000-20000 字的短篇全文
- [ ] draft() 在 target_chars > 8000 时使用分段生成
- [ ] audit() 复用现有 36 条机械规则 + LLM 审计
- [ ] revise() 固定 patch 模式，最多 1 轮
- [ ] export() 输出单文件（支持 tomato_txt/md/epub/qidian_txt）
- [ ] run_full_pipeline() 一键运行全流程
- [ ] 短篇不触发 truth extraction / normalize / approve

### API

- [ ] 8 个端点全部可用（create/get/plan/draft/audit/revise/export/run）
- [ ] `/api/short-stories` 路由前缀独立于 `/api/books`
- [ ] 不存在的短篇返回 404

### 隔离性

- [ ] 长篇管线所有 358 个测试不退步
- [ ] 短篇文件（short_story.json/short_plan.json/short_text.md）不与长篇文件冲突
- [ ] 同一个 book_id 可以是长篇或短篇（通过 short_story.json 是否存在区分）

### 质量门

- [ ] pytest：358+ tests 全绿（新增 ~15 个）
- [ ] ruff check clean
- [ ] 前端 34 tests 不退步

---

## 不在 6B-1 范围内

| 功能 | 归属 | 原因 |
|------|------|------|
| 短篇前端 UI | 6B-2 | 先验证后端管线 |
| 补齐 fanfic/daemon/export 前端 API | 6B-2 | 与短篇前端一起做 |
| 短篇编辑器 | 6B-2 | 先用只读预览 |
| 短篇列表页 | 6B-2 | 先验证单篇流程 |

---

## 参考文件

### 必须读取（理解现有架构）

1. **`src/storyforge3/services/chapter_service.py`** — 长篇管线参考
2. **`src/storyforge3/services/export_service.py`** — 导出逻辑
3. **`src/storyforge3/services/protocols.py`** — Protocol 模式
4. **`src/storyforge3/services/deps.py`** — 依赖注入模式
5. **`src/storyforge3/llm/chunked_generator.py`** — 分段生成
6. **`src/storyforge3/audit/runner.py`** — 机械审计
7. **`src/storyforge3/audit/llm_auditor.py`** — LLM 审计
8. **`src/storyforge3/prompts/registry.py`** — Prompt 注册模式
9. **`src/storyforge3/models.py`** — 现有数据模型
10. **`src/storyforge3/storage.py`** — 存储层 API

### 测试参考

11. **`tests/test_chapter_service.py`** — 管线测试模式
12. **`tests/api/test_books.py`** — API 测试模式

---

## 完成后回报格式

```
给 ClaudeCode 产品经理的执行结果：

Phase 6B-1（短篇管线后端）：

数据模型：
- ShortStoryStatus：[状态 + 枚举值]
- ShortStoryConfig/Meta/Plan/Result：[状态 + 行数]

ShortStoryService：
- create()：[状态]
- plan()：[状态 + prompt 模板名]
- draft()：[状态 + 分段生成阈值]
- audit()：[状态 + 复用了哪些组件]
- revise()：[状态 + 模式 + 最大轮数]
- export()：[状态 + 支持格式]
- run_full_pipeline()：[状态]

API 路由：
- 端点数：[数量]
- 路由前缀：[确认]
- 全部可用：[状态]

隔离性：
- 长篇测试：[数量] passed
- 文件不冲突：[验证方式]

测试：
- 新增测试：[数量] passed
- 后端全量：[数量] passed
- ruff check：[状态]
- 前端：[数量] passed

改动文件列表：[...]
```
