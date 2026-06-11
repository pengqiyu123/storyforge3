# Codex 指令：Phase 7C-2 — Tool 描述分层 + server instructions 增强 + 注册文档

> 发出日期：2026-06-10
> 产品经理：Claude Code PM
> 执行者：Codex
> 前置条件：Phase 7C-1 完成（错误建议 + 输出增强已合并，432+ tests, ruff clean）

---

## 任务概述

为 15 个 MCP tool 的 docstring 增加操作类型标签和工作流引导，增强 server instructions，并提供 Claude Code 注册文档，让 agent 不需要试错就能理解每个 tool 的副作用和耗时，并能让新用户零配置接入。

**当前状态**：
- `tools.py` 15 个 tool 的 docstring 有基本描述和 Args 文档
- 没有操作类型标注（只读/创建/LLM调用/危险操作）
- 没有依赖关系说明（如 `draft_chapter` 前应先 `create_book` + `build_world`）
- 没有注册文档，外部 agent 无法发现和连接 SF3 MCP server

**核心原则**：
1. **标签前缀约定** — 每个 tool docstring 第一行标注 `[只读]` / `[创建]` / `[修改]` / `[LLM 调用]` / `[危险操作]`
2. **docstring 是给 LLM 看的 API 文档** — 必须在 docstring 中回答：做什么？何时用？耗时多久？前置条件？失败怎么办？
3. **注册零配置** — 提供 `claude mcp add` 一行命令和 `.claude/settings.json` 片段，复制即用

---

## Part 1：Tool 描述分层

### 1.1 标签体系

每个 tool docstring 开头必须加标签前缀，格式 `[标签1 标签2]`：

| 标签 | 含义 | 适用 tool |
|------|------|----------|
| `[只读]` | 不修改任何数据，不调用 LLM | `list_books`, `get_book`, `get_chapter_status`, `list_characters`, `get_short_story_status`, `get_truth` |
| `[只读·LLM 调用]` | 不修改数据，但会调用 LLM（审计有 LLM 维度） | `audit_chapter` |
| `[创建·LLM 调用]` | 创建新数据且调用 LLM | `create_book`, `build_world`, `create_character` |
| `[LLM 调用·耗时数分钟]` | 调用 LLM 生成内容，可能耗时较长 | `plan_chapter`, `draft_chapter` |
| `[修改·LLM 调用·耗时数分钟]` | 修改现有数据且调用 LLM | `revise_chapter` |
| `[修改·LLM 调用·耗时较长]` | 完整管线，多个 LLM 调用串联 | `run_short_story` |
| `[创建]` | 生成文件但不调用 LLM | `export_book` |

### 1.2 Docstring 模板

每个 tool docstring 必须包含以下结构：

```python
"""[标签] 一句话描述。

详细说明（1-3 句）。

前置条件：调用前需要满足什么。
建议下一步：调用后建议做什么。

Args:
    param: 参数说明（含有效值范围）。

Returns:
    返回值说明。
"""
```

### 1.3 逐 tool 改写

**文件**：`src/storyforge3/mcp/tools.py`（`register_tools()` 内部函数，lines 246-398）

以下给出每个 tool 的新 docstring，直接替换对应函数的现有 docstring：

#### `list_books`（line 247-252）

```python
"""[只读] 列出工作区中的所有书籍。

返回每本书的 ID、标题、类型、状态和进度信息。无数据时返回空列表。

建议下一步：调用 get_book 查看某本书的详细信息，或调用 create_book 创建新书。

Returns:
    list[BookInfo]: 书籍列表。
"""
```

#### `get_book`（line 255-261）

```python
"""[只读] 获取指定书籍的详细信息。

返回书籍的 ID、标题、类型、状态、当前章节数和目标章节数。

前置条件：book_id 必须存在。可从 list_books 获取有效 ID。
失败时：返回错误信息，建议调用 list_books 查看现有书籍。

Args:
    book_id: 书籍 ID，可从 list_books 获取。

Returns:
    BookInfo: 书籍详细信息。
"""
```

#### `draft_chapter`（line 264-273）

```python
"""[LLM 调用·耗时数分钟] 为指定书籍起草一章。

完整流程：自动规划（plan），然后起草（draft）并返回正文。此操作可能需要 2-5 分钟。

前置条件：书籍已创建（create_book），建议已构建世界观（build_world）和创建角色（create_character）。
建议下一步：调用 audit_chapter 审计章节质量。

Args:
    book_id: 书籍 ID。
    chapter_no: 章节号，从 1 开始。

Returns:
    DraftResult: 包含正文、字数统计和建议下一步。
"""
```

#### `audit_chapter`（line 276-285）

```python
"""[只读·LLM 调用] 审计指定章节。

运行 36 条机械规则 + 4 维 LLM 审计，返回通过/未通过和问题统计。

前置条件：章节已有正文（draft_chapter 或手动编辑）。
建议下一步：审计通过后调用 export_book 导出；未通过则调用 revise_chapter 修订。

Args:
    book_id: 书籍 ID。
    chapter_no: 章节号。

Returns:
    AuditSummary: 包含是否通过、阻断/警告计数和建议下一步。
"""
```

#### `export_book`（line 288-295）

```python
"""[创建] 导出整本书为指定格式。

将所有章节格式化后写入文件。支持番茄小说、Markdown、EPUB、起点中文四种格式。

前置条件：至少有一个章节已完成起草。
建议下一步：导出完成后可继续 draft_chapter 起草下一章。

Args:
    book_id: 书籍 ID。
    fmt: 导出格式，支持 tomato_txt、md、epub、qidian_txt。

Returns:
    ExportResult: 包含导出文件路径和格式。
"""
```

#### `create_book`（line 298-308）

```python
"""[创建] 创建新书。

在当前工作区中创建一本新书，初始化目录结构和配置文件。

前置条件：title 不能为空，genre 和 platform 必须是有效值。
建议下一步：调用 build_world 构建世界观，再调用 create_character 创建角色。

Args:
    title: 书名。
    genre: 类型，支持 xuanhuan（玄幻）、xianxia（仙侠）、urban（都市）、horror（恐怖）、other（其他）。
    platform: 平台，支持 tomato（番茄）、feilu（飞卢）、qidian（起点）、other（其他）。
    target_chapters: 目标章节数。
    chapter_word_count: 每章目标字数。

Returns:
    BookInfo: 新创建的书籍信息。
"""
```

#### `plan_chapter`（line 311-318）

```python
"""[LLM 调用·耗时数分钟] 为指定章节生成规划。

基于世界观、角色和前文上下文，生成章节目标、卷纲节点、必须保留和必须避免。

前置条件：书籍已创建（create_book），建议已构建世界观（build_world）。
建议下一步：调用 draft_chapter 根据规划起草正文。

Args:
    book_id: 书籍 ID。
    chapter_no: 章节号。

Returns:
    ChapterPlanInfo: 包含章节目标、卷纲节点、必须保留和必须避免。
"""
```

#### `revise_chapter`（line 321-329）

```python
"""[修改·LLM 调用·耗时数分钟] 修订章节。

根据审计结果修订章节正文。支持 6 种模式。auto 模式自动推荐最合适的修订策略。

前置条件：章节已审计且存在问题（audit_chapter 返回 passed=false）。
建议下一步：修订后调用 audit_chapter 重新审计确认质量。最多修订 2 轮。

Args:
    book_id: 书籍 ID。
    chapter_no: 章节号。
    mode: 修订模式 — auto（自动推荐）、polish（润色）、spot_fix（定点修复）、anti_detect（去 AI 痕迹）、surgical（精细手术）、rework（全文重写，不可逆）。

Returns:
    ChapterStatusInfo: 包含修订后状态和建议下一步。
"""
```

#### `get_chapter_status`（line 332-339）

```python
"""[只读] 查询章节当前状态。

返回章节的状态、标题、是否有正文等基础信息。不触发任何操作。

建议下一步：根据 next_step 字段的建议执行对应操作。

Args:
    book_id: 书籍 ID。
    chapter_no: 章节号。

Returns:
    ChapterStatusInfo: 包含状态信息和下一步建议。
"""
```

#### `build_world`（line 342-350）

```python
"""[创建·LLM 调用] 构建世界观。

基于类型和种子描述，生成世界观设定、力量体系、核心冲突和基本规则。

前置条件：书籍已创建（create_book）。
建议下一步：调用 create_character 创建角色，再调用 plan_chapter 规划章节。

Args:
    book_id: 书籍 ID。
    genre: 类型，如 xuanhuan、xianxia、urban、horror、other。
    seed: 世界观种子描述，自由文本，如"近未来都市+存在感系统+异常机构"。

Returns:
    WorldInfo: 包含世界观描述、力量体系、核心冲突和规则列表。
"""
```

#### `create_character`（line 353-360）

```python
"""[创建·LLM 调用] 用自然语言描述创建角色。

根据描述生成角色名、定位、性格、档案和能力列表，并保存到书籍配置中。

前置条件：书籍已创建（create_book）。
建议下一步：可继续调用 create_character 创建更多角色，或调用 list_characters 查看已有角色。

Args:
    book_id: 书籍 ID。
    spec: 角色描述，自由文本，如"18岁男高中生，性格谨慎，有存在感调节能力"。

Returns:
    CharacterInfo: 包含角色名、定位、性格、档案和能力列表。
"""
```

#### `list_characters`（line 363-369）

```python
"""[只读] 列出书中的所有角色。

返回书中已创建的所有角色信息。

前置条件：书籍已创建（create_book）。

Args:
    book_id: 书籍 ID。

Returns:
    list[CharacterInfo]: 角色列表。
"""
```

#### `run_short_story`（line 372-380）

```python
"""[修改·LLM 调用·耗时较长] 一键运行短篇全流程。

完整流程：规划→起草→审计→修订→导出。此操作可能需要 10-30 分钟，期间会执行多次 LLM 调用。

前置条件：短篇已创建（create_book）。
建议下一步：调用 get_short_story_status 查询执行进度。

Args:
    book_id: 短篇 ID。

Returns:
    ShortStoryStatusInfo: 包含最终状态和建议下一步。
"""
```

#### `get_short_story_status`（line 383-389）

```python
"""[只读] 查询短篇当前状态。

返回短篇的状态、是否有正文、当前字数等基础信息。不触发任何操作。

建议下一步：根据 next_step 字段的建议执行对应操作。

Args:
    book_id: 短篇 ID。

Returns:
    ShortStoryStatusInfo: 包含状态信息和下一步建议。
"""
```

#### `get_truth`（line 392-398）

```python
"""[只读] 获取最新 truth 数据，用于跨章连续性检查。

返回最近一次 truth 提取的事实断言、角色变化、不可逆事实等数据。

前置条件：至少有一个章节完成了审计（audit_chapter 通过或修订后通过）。
建议下一步：truth 数据会自动用于后续 draft_chapter 的上下文，无需手动传递。

Args:
    book_id: 书籍 ID。

Returns:
    TruthInfo: 包含事实断言、角色变化和不可逆事实。
"""
```

---

## Part 2：server.py instructions 增强

### 2.1 更新 FastMCP instructions

**文件**：`src/storyforge3/mcp/server.py`（line 37）

当前 instructions 只有一句话。扩展为工作流引导：

```python
mcp = FastMCP(
    "StoryForge",
    instructions=(
        "StoryForge3 网文创作引擎。支持长篇（逐章管线）和短篇（一键生成）。\n"
        "长篇工作流：create_book → build_world → create_character → plan_chapter → draft_chapter → audit_chapter → revise_chapter（最多2轮）→ export_book。\n"
        "短篇工作流：create_book → run_short_story（一键全流程）。\n"
        "每个 tool 的描述中标注了操作类型：[只读] 安全可随时调用；[LLM 调用] 需要等待；[修改] 会改变数据。"
    ),
)
```

---

## Part 3：Claude Code 注册文档

### 3.1 新建注册文档

**新文件**：`docs/mcp-registration.md`

内容：

```markdown
# StoryForge3 MCP Server — Claude Code 注册指南

## 快速注册

在终端中运行：

```bash
claude mcp add storyforge3 -- python -m storyforge3.mcp
```

注册后，Claude Code 会自动发现并使用 StoryForge3 的 15 个创作工具。

## 手动配置

如果自动注册不生效，可将以下片段添加到项目 `.claude/settings.json`：

```json
{
  "mcpServers": {
    "storyforge3": {
      "command": "python",
      "args": ["-m", "storyforge3.mcp"],
      "cwd": "D:\\python\\Novel\\storyforge3"
    }
  }
}
```

> 注意：`cwd` 路径需要替换为你的实际 StoryForge3 安装目录。

## 验证注册

在 Claude Code 中输入：

```
请调用 list_books 查看工作区中的书籍。
```

如果 Claude Code 成功调用了 `list_books` tool，说明注册成功。

## 可用工具

| Tool | 类型 | 说明 |
|------|------|------|
| `list_books` | 只读 | 列出所有书籍 |
| `get_book` | 只读 | 获取书籍详情 |
| `create_book` | 创建 | 创建新书 |
| `build_world` | 创建·LLM | 构建世界观 |
| `create_character` | 创建·LLM | 创建角色 |
| `list_characters` | 只读 | 列出角色 |
| `plan_chapter` | LLM·耗时 | 生成章节规划 |
| `draft_chapter` | LLM·耗时 | 起草章节正文 |
| `audit_chapter` | 只读·LLM | 审计章节质量 |
| `revise_chapter` | 修改·LLM·耗时 | 修订章节 |
| `get_chapter_status` | 只读 | 查询章节状态 |
| `export_book` | 创建 | 导出为指定格式 |
| `run_short_story` | 修改·LLM·耗时较长 | 短篇一键全流程 |
| `get_short_story_status` | 只读 | 查询短篇状态 |
| `get_truth` | 只读 | 获取跨章 truth 数据 |

## 工作流示例

### 长篇创作

```
1. create_book(title="我是路人甲", genre="urban", platform="tomato", target_chapters=100, chapter_word_count=2500)
2. build_world(book_id="lurenjia", genre="urban", seed="近未来都市+存在感系统+异常机构")
3. create_character(book_id="lurenjia", spec="18岁男高中生，性格谨慎，有存在感调节能力")
4. plan_chapter(book_id="lurenjia", chapter_no=1)
5. draft_chapter(book_id="lurenjia", chapter_no=1)
6. audit_chapter(book_id="lurenjia", chapter_no=1)
7. revise_chapter(book_id="lurenjia", chapter_no=1)  # 如果审计未通过
8. export_book(book_id="lurenjia", fmt="tomato_txt")
```

### 短篇创作

```
1. create_book(title="深夜便利店", genre="horror", platform="tomato", target_chapters=1, chapter_word_count=8000)
2. run_short_story(book_id="short-night")
```
```

---

## Part 4：借鉴来源

| 借鉴内容 | 来源文件 | 行数 | 借鉴方式 |
|---------|---------|------|---------|
| **MCP 注册命令模式** | CC-Switch `docs/user-manual/en/3-extensions/3.1-mcp.md:32-56` | ~24 行 | **骨架移植**：字段结构（ID/Name/Transport/Command），适配为 Python 单行命令 |
| **MCP 配置 JSON 格式** | CC-Switch `src-tauri/src/claude_mcp.rs:387-446` `set_mcp_servers_map()` | ~60 行 | **直接复用** `mcpServers` JSON 结构，替换 command/args/cwd |
| **Tool 描述模板** | CC-Switch MCP 预设模板描述格式 | ~10 行 | **模式复用**：标签+描述+参数+返回值 |
| **工作流说明** | InkOS `packages/cli/src/interaction/tools.ts` 工具编排 | ~26 行 | **模式复用**：create → build → draft → audit → revise → export |

**新写比例**：约 **30%**。Docstring 内容需要针对每个 tool 手写（这是 LLM 面向的 API 文档，不能模板生成），注册文档结构复用 CC-Switch 的 MCP 配置模式。

### 移植适配清单

| 源项目原始 | SF3 适配 |
|-----------|---------|
| CC-Switch MCP 配置用 `command: "npx"` / `args: ["-y", "@anthropic/mcp-server"]` | 替换为 `command: "python"` / `args: ["-m", "storyforge3.mcp"]` |
| CC-Switch MCP 配置写入 `~/.claude.json` | SF3 推荐项目级 `.claude/settings.json`（更安全） |
| CC-Switch 文档用英文 | SF3 用中文（目标用户是中文作者） |
| CC-Switch tool 表格按功能分组 | SF3 按操作类型标注 |

---

## 验收标准

### Tool 描述

- [ ] 15 个 tool 的 docstring 全部包含标签前缀（`[只读]` / `[创建]` / `[LLM 调用]` 等）
- [ ] 每个 docstring 包含前置条件说明
- [ ] 有副作用的 tool（创建/修改/LLM调用）包含建议下一步
- [ ] 6 个只读 tool 标注为 `[只读]`
- [ ] `revise_chapter` 的 `rework` 模式在描述中提及不可逆性
- [ ] `run_short_story` 描述中包含耗时估计（10-30 分钟）

### Server instructions

- [ ] `server.py` 的 FastMCP instructions 包含长篇和短篇工作流说明
- [ ] 包含标签体系说明

### 注册文档

- [ ] `docs/mcp-registration.md` 包含 `claude mcp add` 一行命令
- [ ] 包含 `.claude/settings.json` 手动配置片段
- [ ] 包含验证步骤
- [ ] 包含 15 个 tool 速查表
- [ ] 包含长篇和短篇工作流示例

### 测试

- [ ] `test_register_tools_adds_fifteen_tools` 仍然通过（docstring 不影响注册）
- [ ] 现有 432+ tests 不退步

### 质量

- [ ] `ruff check .` clean
- [ ] Docstring 格式一致（标签 + 描述 + 前置条件 + 建议下一步 + Args + Returns）

---

## 估算工作量

| 部分 | 文件 | 预估行数 |
|------|------|---------|
| 15 个 tool docstring 改写 | `mcp/tools.py` | ~150 行改动（替换现有 docstring） |
| server.py instructions | `mcp/server.py` | ~5 行改动 |
| 注册文档 | `docs/mcp-registration.md` | ~80 行新增 |
| 测试更新 | `tests/test_mcp_server.py` | ~5 行改动（如有 match 变化） |
| **合计** | **4 个文件** | **~240 行** |

---

## 不做的事（Out of Scope）

- ❌ 不改 tool 的输入输出签名（7C-1 负责）
- ❌ 不改错误消息（7C-1 负责）
- ❌ 不引入新依赖
- ❌ 不做 SSE transport（当前 STDIO 足够）
- ❌ 不做 tool 权限控制（所有 tool 对所有 agent 开放）
- ❌ 不改 Service / Protocol 层
