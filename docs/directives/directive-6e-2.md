# Codex 指令：Phase 6E-2 — MCP Server 工具扩展

> 发出日期：2026-06-10
> 产品经理：Claude Code PM
> 执行者：Codex
> 前置条件：Phase 6E-1 完成（383 后端 tests, 39 前端 tests, ruff clean, MCP STDIO 跑通 5 tool）

---

## 任务概述

Phase 6E-1 交付了 MCP Server 基础框架 + 5 个核心 tool（list_books/get_book/draft_chapter/audit_chapter/export_book）+ STDIO transport。本阶段扩展更多实用 tool，让外部 AI（Claude Code、Codex）能真正参与创作的全流程管理。

**核心原则**：
1. 聚焦"工具能力扩展"，不涉及 SSE/HTTP transport 和认证（留给后续）
2. 复用 6E-1 建立的 `register_tools()` + 独立 tool 函数 + Pydantic 输出模型模式
3. 每个 tool 调用真实 SF3 服务方法，MCP 层是薄封装
4. 新增 service 依赖通过闭包注入，与 6E-1 一致

---

## 新增 Tool 列表（10 个）

### Tier 1：长篇管线补充（4 个）

| # | Tool 名 | 调用的 Service 方法 | 类型 | 说明 |
|---|---------|---------------------|------|------|
| 1 | `create_book` | `BookService.create(config)` | LLM-无关, 快速 | 创建新书，返回 BookMeta |
| 2 | `plan_chapter` | `ChapterService.plan(book_id, chapter_no)` | LLM, 慢 | 单独规划章节，返回 ChapterIntent |
| 3 | `revise_chapter` | `ChapterService.revise(book_id, chapter_no, mode)` | LLM, 慢 | 修订章节（5 种模式），返回 ChapterResult |
| 4 | `get_chapter_status` | `ChapterService.get_status(book_id, chapter_no)` | LLM-无关, 快速 | 查询章节当前状态 |

### Tier 2：世界观 + 角色（3 个）

| # | Tool 名 | 调用的 Service 方法 | 类型 | 说明 |
|---|---------|---------------------|------|------|
| 5 | `build_world` | `WorldService.build(book_id, genre, seed_brief)` | LLM, 慢 | 构建世界观（设定/力量体系/冲突/规则） |
| 6 | `create_character` | `CharacterService.create(book_id, spec)` | LLM, 慢 | 用自然语言描述创建角色 |
| 7 | `list_characters` | `CharacterService.list_characters(book_id)` | LLM-无关, 快速 | 列出书中的所有角色 |

### Tier 3：短篇管线（2 个）

| # | Tool 名 | 调用的 Service 方法 | 类型 | 说明 |
|---|---------|---------------------|------|------|
| 8 | `run_short_story` | `ShortStoryService.run_full_pipeline(book_id)` | LLM, 慢 | 一键运行短篇全流程（plan→draft→audit→revise→export） |
| 9 | `get_short_story_status` | `ShortStoryService.get_status(book_id)` | LLM-无关, 快速 | 查询短篇当前状态 |

### Tier 4：Truth 查询（1 个）

| # | Tool 名 | 调用的 Service 方法 | 类型 | 说明 |
|---|---------|---------------------|------|------|
| 10 | `get_truth` | `TruthService.load_latest(book_id)` | LLM-无关, 快速 | 获取最新的 truth 数据（连续性事实） |

---

## 详细 Tool 定义

### `tools.py` 新增内容

```python
# ── 新增 Pydantic 输出模型 ────────────────────────────────────

class ChapterPlanInfo(BaseModel):
    """章节规划结果。"""
    chapter_no: int = Field(description="章节号")
    goal: str = Field(description="本章目标")
    outline_node: str = Field(description="卷纲节点")
    must_keep: list[str] = Field(description="必须保留")
    must_avoid: list[str] = Field(description="必须避免")

class ChapterStatusInfo(BaseModel):
    """章节状态。"""
    book_id: str
    chapter_no: int
    status: str
    title: str
    has_text: bool
    error: str | None = None

class WorldInfo(BaseModel):
    """世界观设定。"""
    book_id: str
    setting: str = Field(description="世界观描述")
    power_system: str = Field(description="力量体系")
    core_conflict: str = Field(description="核心冲突")
    rules: list[str] = Field(description="基本规则列表")

class CharacterInfo(BaseModel):
    """角色信息。"""
    name: str
    role: str = Field(description="角色定位：protagonist/major/minor")
    personality: str
    profile: str
    abilities: list[str]

class ShortStoryStatusInfo(BaseModel):
    """短篇状态。"""
    book_id: str
    status: str
    has_text: bool
    actual_chars: int
    error: str | None = None

class TruthInfo(BaseModel):
    """Truth 连续性数据。"""
    chapter_no: int
    source: str
    fact_assertions: list[str] = Field(description="事实断言")
    character_updates: list[str] = Field(description="角色变化摘要")
    irreversible_facts: list[str] = Field(description="不可逆事实")
```

### 新增 Tool 函数

```python
# ── Tier 1: 长篇管线补充 ─────────────────────────────────────

async def create_book_tool(books, title: str, genre: str, platform: str,
                           target_chapters: int, chapter_word_count: int) -> BookInfo:
    config = BookConfig(title=title, genre=genre, platform=platform,
                        target_chapters=target_chapters,
                        chapter_word_count=chapter_word_count)
    meta = await books.create(config)
    return BookInfo(
        book_id=meta.book_id, title=meta.title, genre=meta.genre,
        status=meta.status.value, current_chapter=meta.current_chapter,
        target_chapters=meta.target_chapters,
    )

async def plan_chapter_tool(chapters, book_id: str, chapter_no: int) -> ChapterPlanInfo:
    intent = await chapters.plan(book_id, chapter_no)
    return ChapterPlanInfo(
        chapter_no=intent.chapter_no, goal=intent.goal,
        outline_node=intent.outline_node,
        must_keep=list(intent.must_keep),
        must_avoid=list(intent.must_avoid),
    )

async def revise_chapter_tool(chapters, book_id: str, chapter_no: int,
                               mode: str = "auto") -> ChapterStatusInfo:
    result = await chapters.revise(book_id, chapter_no, mode)
    return ChapterStatusInfo(
        book_id=result.book_id, chapter_no=result.chapter_no,
        status=result.status.value, title=result.title,
        has_text=bool(result.text), error=result.error,
    )

async def get_chapter_status_tool(chapters, book_id: str, chapter_no: int) -> ChapterStatusInfo:
    result = await chapters.get_status(book_id, chapter_no)
    if result is None:
        raise ValueError(f"章节不存在: {book_id} #{chapter_no}")
    return ChapterStatusInfo(
        book_id=result.book_id, chapter_no=result.chapter_no,
        status=result.status.value, title=result.title,
        has_text=bool(result.text), error=result.error,
    )

# ── Tier 2: 世界观 + 角色 ───────────────────────────────────

async def build_world_tool(world_service, book_id: str, genre: str, seed: str) -> WorldInfo:
    world = await world_service.build(book_id, genre, seed)
    return WorldInfo(
        book_id=world.book_id, setting=world.setting,
        power_system=world.power_system,
        core_conflict=world.core_conflict,
        rules=list(world.rules),
    )

async def create_character_tool(character_service, book_id: str, spec: str) -> CharacterInfo:
    char = await character_service.create(book_id, spec)
    return CharacterInfo(
        name=char.name, role=char.role.value,
        personality=char.personality, profile=char.profile,
        abilities=list(char.abilities),
    )

async def list_characters_tool(character_service, book_id: str) -> list[CharacterInfo]:
    chars = await character_service.list_characters(book_id)
    return [
        CharacterInfo(
            name=c.name, role=c.role.value, personality=c.personality,
            profile=c.profile, abilities=list(c.abilities),
        )
        for c in chars
    ]

# ── Tier 3: 短篇管线 ──────────────────────────────────────────

async def run_short_story_tool(short_service, book_id: str) -> ShortStoryStatusInfo:
    result = await short_service.run_full_pipeline(book_id)
    return ShortStoryStatusInfo(
        book_id=result.book_id, status=result.status.value,
        has_text=bool(result.text), actual_chars=len(result.text),
        error=result.error,
    )

async def get_short_story_status_tool(short_service, book_id: str) -> ShortStoryStatusInfo:
    result = short_service.get_status(book_id)
    if result is None:
        raise ValueError(f"短篇不存在: {book_id}")
    return ShortStoryStatusInfo(
        book_id=result.book_id, status=result.status.value,
        has_text=bool(result.text), actual_chars=len(result.text),
        error=result.error,
    )

# ── Tier 4: Truth 查询 ───────────────────────────────────────

async def get_truth_tool(truth_service, book_id: str) -> TruthInfo:
    truth = truth_service.load_latest(book_id)
    if truth is None:
        raise ValueError(f"暂无 truth 数据: {book_id}")
    return TruthInfo(
        chapter_no=truth.chapter_no, source=truth.source,
        fact_assertions=list(truth.fact_assertions),
        character_updates=[str(u) for u in truth.character_updates],
        irreversible_facts=list(truth.irreversible_facts),
    )
```

### `register_tools()` 扩展

```python
def register_tools(mcp, books, chapters, exports,
                   world_service, character_service,
                   short_service, truth_service) -> None:
    # ... 保留原有 5 个 tool ...

    @mcp.tool()
    async def create_book(title: str, genre: str, platform: str,
                          target_chapters: int, chapter_word_count: int) -> BookInfo:
        """创建新书。

        Args:
            title: 书名
            genre: 类型（xuanhuan/xianxia/urban/horror/other）
            platform: 平台（tomato/feilu/qidian/other）
            target_chapters: 目标章节数
            chapter_word_count: 每章目标字数
        """
        return await create_book_tool(books, title, genre, platform,
                                       target_chapters, chapter_word_count)

    @mcp.tool()
    async def plan_chapter(book_id: str, chapter_no: int) -> ChapterPlanInfo:
        """为指定章节生成规划（目标、卷纲节点、必须保留/避免的内容）。

        Args:
            book_id: 书籍 ID
            chapter_no: 章节号
        """
        return await plan_chapter_tool(chapters, book_id, chapter_no)

    @mcp.tool()
    async def revise_chapter(book_id: str, chapter_no: int,
                              mode: str = "auto") -> ChapterStatusInfo:
        """修订章节。支持 5 种模式：auto/polish/spot_fix/anti_detect/surgical/rework。

        Args:
            book_id: 书籍 ID
            chapter_no: 章节号
            mode: 修订模式（默认 auto 自动推荐）
        """
        return await revise_chapter_tool(chapters, book_id, chapter_no, mode)

    @mcp.tool()
    async def get_chapter_status(book_id: str, chapter_no: int) -> ChapterStatusInfo:
        """查询章节当前状态。

        Args:
            book_id: 书籍 ID
            chapter_no: 章节号
        """
        return await get_chapter_status_tool(chapters, book_id, chapter_no)

    @mcp.tool()
    async def build_world(book_id: str, genre: str, seed: str) -> WorldInfo:
        """构建世界观（AI 生成设定、力量体系、核心冲突和规则）。

        Args:
            book_id: 书籍 ID
            genre: 类型
            seed: 世界观种子描述（自然语言）
        """
        return await build_world_tool(world_service, book_id, genre, seed)

    @mcp.tool()
    async def create_character(book_id: str, spec: str) -> CharacterInfo:
        """用自然语言描述创建角色。AI 会根据描述生成完整的角色档案。

        Args:
            book_id: 书籍 ID
            spec: 角色描述（如"18岁男高中生，性格内向，有存在感系统"）
        """
        return await create_character_tool(character_service, book_id, spec)

    @mcp.tool()
    async def list_characters(book_id: str) -> list[CharacterInfo]:
        """列出书中的所有角色。

        Args:
            book_id: 书籍 ID
        """
        return await list_characters_tool(character_service, book_id)

    @mcp.tool()
    async def run_short_story(book_id: str) -> ShortStoryStatusInfo:
        """一键运行短篇全流程（规划→起草→审计→修订→导出）。

        注意：此操作可能需要较长时间（LLM 多次调用）。

        Args:
            book_id: 短篇 ID
        """
        return await run_short_story_tool(short_service, book_id)

    @mcp.tool()
    async def get_short_story_status(book_id: str) -> ShortStoryStatusInfo:
        """查询短篇当前状态。

        Args:
            book_id: 短篇 ID
        """
        return await get_short_story_status_tool(short_service, book_id)

    @mcp.tool()
    async def get_truth(book_id: str) -> TruthInfo:
        """获取最新的 truth 数据（跨章连续性事实和角色变化）。

        Args:
            book_id: 书籍 ID
        """
        return await get_truth_tool(truth_service, book_id)
```

---

## 服务组装扩展

### `server.py` 修改

```python
def create_server() -> FastMCP:
    config = StoryForge3Config()
    paths = StoragePaths(Path(config.books_dir))
    storage = BookStorage(paths.books_root)

    book_service = BookService(storage, paths)
    chapter_service = ChapterService(config, storage=storage, paths=paths,
                                      pipeline_logger=PipelineLogger(config.books_dir))
    export_service = ExportService(storage, paths)
    world_service = WorldService(create_llm_service(config), storage, paths, config)
    character_service = CharacterService(create_llm_service(config), storage, paths, config)
    short_service = ShortStoryService(config, storage=storage, paths=paths)
    truth_service = TruthService(config=config)

    mcp = FastMCP("StoryForge", instructions="...")
    register_tools(mcp, book_service, chapter_service, export_service,
                   world_service, character_service, short_service, truth_service)
    return mcp
```

**新增依赖**：`WorldService`, `CharacterService`, `ShortStoryService`, `TruthService`, `create_llm_service`。

**注意**：`WorldService` 和 `CharacterService` 各自需要独立的 `create_llm_service(config)` 实例（与 `ChapterService` 的 LLM 实例独立）。

---

## 文件改动清单

### 修改

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/storyforge3/mcp/tools.py` | 修改 | 新增 10 个 tool 函数 + 6 个 Pydantic 模型 + `register_tools()` 签名扩展 |
| `src/storyforge3/mcp/server.py` | 修改 | 新增 4 个 service 实例化 |
| `tests/test_mcp_server.py` | 修改 | 新增 ~10 个 tool 测试 |

**新增行数**：~300 行（tools.py ~200, server.py ~15, tests ~100）

---

## 测试

### 新增测试要点

```python
# Tier 1
test_create_book_tool_creates_book
test_plan_chapter_tool_returns_plan_info
test_revise_chapter_tool_calls_service
test_get_chapter_status_tool_returns_status
test_get_chapter_status_tool_not_found

# Tier 2
test_build_world_tool_returns_world_info
test_create_character_tool_returns_character
test_list_characters_tool_returns_list

# Tier 3
test_run_short_story_tool_calls_pipeline
test_get_short_story_status_tool_not_found

# Tier 4
test_get_truth_tool_returns_truth
test_get_truth_tool_no_data

# 注册验证
test_register_tools_adds_fifteen_tools  # 原 5 + 新 10
```

### 验证命令

```powershell
cd storyforge3
.\.venv\Scripts\python.exe -m pytest tests/ -q   # 395+ tests
ruff check .
```

---

## 验收标准

### Tool 注册

- [ ] 总计 15 个 tool（原 5 + 新 10）
- [ ] 每个 tool 有中文 docstring + 参数说明
- [ ] `register_tools()` 签名扩展正确

### Tool 行为

- [ ] `create_book` 创建新书并返回 BookInfo
- [ ] `plan_chapter` 返回 ChapterPlanInfo
- [ ] `revise_chapter` 调用 ChapterService.revise
- [ ] `get_chapter_status` 返回章节状态，不存在时返回错误
- [ ] `build_world` 调用 WorldService.build
- [ ] `create_character` 调用 CharacterService.create
- [ ] `list_characters` 返回角色列表
- [ ] `run_short_story` 调用 ShortStoryService.run_full_pipeline
- [ ] `get_short_story_status` 返回短篇状态
- [ ] `get_truth` 返回最新 truth 数据，无数据时返回错误

### 隔离性

- [ ] 383 后端 tests 不退步
- [ ] 39 前端 tests 不退步
- [ ] ruff check clean
- [ ] 现有 service/model/API 零改动

### 测试

- [ ] 新增 ~13 个 MCP 测试
- [ ] pytest 全量 396+ tests passed

---

## 不在 6E-2 范围内

| 功能 | 归属 | 原因 |
|------|------|------|
| SSE/HTTP transport | 后续 | STDIO 已够用，SSE 是部署形态 |
| 认证/Token | 后续 | 本地进程通信不需要 |
| Claude Code 注册脚本 | 后续 | 框架稳定后 |
| volume_service tools | 后续 | 卷纲管理优先级低于世界/角色 |
| fanfic_service tools | 后续 | 同人模式后端已有，MCP 暂缓 |
| daemon_service tools | 后续 | 批处理风险高，需要更多设计 |
| 进度报告（progress） | 后续 | 先做基本功能 |

---

## 参考文件

### 必须读取

1. **`src/storyforge3/mcp/tools.py`** — 现有 5 个 tool + 模式
2. **`src/storyforge3/mcp/server.py`** — 现有服务组装
3. **`src/storyforge3/services/book_service.py`** — `create()` 签名
4. **`src/storyforge3/services/chapter_service.py`** — `plan/revise/get_status` 签名
5. **`src/storyforge3/services/world_service.py`** — `build()` 签名
6. **`src/storyforge3/services/character_service.py`** — `create/list_characters` 签名
7. **`src/storyforge3/services/short_story_service.py`** — `run_full_pipeline/get_status` 签名
8. **`src/storyforge3/services/truth_service.py`** — `load_latest` 签名
9. **`tests/test_mcp_server.py`** — 现有测试模式

---

## 完成后回报格式

```
给 ClaudeCode 产品经理的执行结果：

Phase 6E-2（MCP Server 工具扩展）：

Tool 注册：
- 总计：[数量] 个 tool
- 新增 tool：[列表 + 各自状态]

服务组装：
- 新增 services：[列表]
- register_tools 签名：[确认]

测试：
- 新增 MCP 测试：[数量] passed
- 后端全量：[数量] passed
- 前端：[数量] passed
- ruff check：[状态]

改动文件列表：[...]
```
