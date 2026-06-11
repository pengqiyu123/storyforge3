# Codex 指令：Phase 7C-1 — MCP 错误建议 + 输出增强

> 发出日期：2026-06-10
> 产品经理：Claude Code PM
> 执行者：Codex
> 前置条件：Phase 7B-3 完成（432 后端 tests + 59 前端 tests, ruff clean）

---

## 任务概述

让 15 个 MCP tool 的错误信息和返回值对 LLM agent（Claude Code / Codex）真正有用。当前痛点：

1. **错误只说"不存在"，不告诉 agent 下一步该做什么** — agent 收到 `ValueError("书籍不存在: missing")` 后不知道该 `list_books` 还是 `create_book`
2. **返回值缺少工作流上下文** — `get_chapter_status` 返回 `status=drafted`，但 agent 不知道接下来应该 `audit_chapter`
3. **draft_chapter 返回纯文本** — agent 看不到字数，不知道是否达标

**当前状态**：
- `tools.py` 15 个 tool 全部注册，20 个测试通过
- 4 个 ValueError 位置（lines 124, 193, 226, 233）只有诊断信息，无恢复建议
- 6 个输出模型（BookInfo / AuditSummary / ChapterStatusInfo / WorldInfo / ShortStoryStatusInfo / TruthInfo）无 `next_step` 字段
- `draft_chapter` 返回 `str`，无结构化信息

**核心原则**：
1. **错误 = 诊断 + 恢复建议** — 每个 ValueError 必须告诉 agent 可以调哪个 tool 解决
2. **输出 = 数据 + 工作流提示** — 关键 tool 返回 `next_step` 字段引导 agent 继续操作
3. **不改 Protocol / Service 层** — 只改 MCP 层的 tools.py 及其数据模型

---

## Part 1：错误信息增强

### 1.1 四个 ValueError 位置修改

**文件**：`src/storyforge3/mcp/tools.py`

**位置 1 — line 124**（`get_book_tool`）：

```python
# 现有
raise ValueError(f"书籍不存在: {book_id}")

# 改为
raise ValueError(f"书籍不存在: {book_id}。请先调用 list_books 查看现有书籍，或调用 create_book 创建新书。")
```

**位置 2 — line 193**（`get_chapter_status_tool`）：

```python
# 现有
raise ValueError(f"章节不存在: {book_id} #{chapter_no}")

# 改为
raise ValueError(f"章节不存在: {book_id} #{chapter_no}。请先调用 get_book 检查当前章节数，再调用 draft_chapter 创建章节。")
```

**位置 3 — line 226**（`get_short_story_status_tool`）：

```python
# 现有
raise ValueError(f"短篇不存在: {book_id}")

# 改为
raise ValueError(f"短篇不存在: {book_id}。请先调用 list_books 查看现有书籍，确认 book_id 正确。")
```

**位置 4 — line 233**（`get_truth_tool`）：

```python
# 现有
raise ValueError(f"暂无 truth 数据: {book_id}")

# 改为
raise ValueError(f"暂无 truth 数据: {book_id}。请先调用 draft_chapter 起草章节，再调用 audit_chapter 审计后自动提取 truth。")
```

---

## Part 2：输出模型增强

### 2.1 `ChapterStatusInfo` 增加 `next_step`

**文件**：`src/storyforge3/mcp/tools.py`（lines 51-59）

```python
class ChapterStatusInfo(BaseModel):
    """Chapter status returned by MCP tools."""

    book_id: str = Field(description="书籍 ID")
    chapter_no: int = Field(description="章节号")
    status: str = Field(description="状态")
    title: str = Field(description="章节标题")
    has_text: bool = Field(description="是否已有正文")
    error: str | None = Field(default=None, description="错误信息")
    next_step: str | None = Field(default=None, description="建议下一步操作")
```

### 2.2 `next_step` 填充逻辑

在 `_chapter_status_info()` 辅助函数中根据 status 填充：

```python
def _chapter_status_info(result) -> ChapterStatusInfo:
    status_val = result.status.value if hasattr(result.status, "value") else str(result.status)
    next_step = _suggest_next_step(status_val)
    return ChapterStatusInfo(
        book_id=result.book_id,
        chapter_no=result.chapter_no,
        status=status_val,
        title=result.title,
        has_text=bool(result.text),
        error=result.error,
        next_step=next_step,
    )


def _suggest_next_step(status: str) -> str | None:
    """根据章节状态返回建议下一步操作。"""
    mapping = {
        "planned": "调用 draft_chapter 起草正文。",
        "drafted": "调用 audit_chapter 进行审计。",
        "audited_passed": "调用 export_book 导出，或继续 draft_chapter 起草下一章。",
        "audited_failed": "调用 revise_chapter 修订章节。",
        "revised": "调用 audit_chapter 重新审计。",
        "needs_review": "章节已手动编辑，可调用 audit_chapter 审计确认质量。",
        "exported": "章节已导出。可继续 draft_chapter 起草下一章。",
    }
    return mapping.get(status)
```

**注意**：此映射覆盖 7 种已知状态。未匹配状态返回 `None`（不显示建议），未来新增状态自动优雅降级。

### 2.3 `AuditSummary` 增加 `next_step`

**文件**：`src/storyforge3/mcp/tools.py`（lines 25-32）

```python
class AuditSummary(BaseModel):
    """Compact audit result for one chapter."""

    chapter_no: int = Field(description="章节号")
    passed: bool = Field(description="是否通过")
    blocking_count: int = Field(description="阻断性问题数")
    warning_count: int = Field(description="警告数")
    next_step: str = Field(description="建议下一步操作")
```

在 `audit_chapter_tool()` 中填充：

```python
async def audit_chapter_tool(chapters, book_id: str, chapter_no: int) -> AuditSummary:
    result = await chapters.audit(book_id, chapter_no)
    next_step = (
        "审计通过。可调用 export_book 导出，或继续 draft_chapter 起草下一章。"
        if result.passed
        else f"审计未通过（{len(result.blocking_issues)} 个阻断性问题）。请调用 revise_chapter 修订章节。"
    )
    return AuditSummary(
        chapter_no=result.chapter_no,
        passed=result.passed,
        blocking_count=len(result.blocking_issues),
        warning_count=len(result.warnings),
        next_step=next_step,
    )
```

### 2.4 `draft_chapter` 返回结构化数据

**当前**：返回 `str`（纯正文）。**改为**：返回 `DraftResult` 模型。

```python
class DraftResult(BaseModel):
    """Draft output returned by MCP tools."""

    chapter_no: int = Field(description="章节号")
    text: str = Field(description="章节正文")
    char_count: int = Field(description="中文字符数")
    next_step: str = Field(description="建议下一步操作")
```

修改 `draft_chapter_tool()`：

```python
async def draft_chapter_tool(chapters, book_id: str, chapter_no: int) -> DraftResult:
    intent = await chapters.plan(book_id, chapter_no)
    text = await chapters.draft(book_id, chapter_no, intent)
    chinese_chars = sum(1 for ch in text if "一" <= ch <= "鿿")
    return DraftResult(
        chapter_no=chapter_no,
        text=text,
        char_count=chinese_chars,
        next_step=f"起草完成，共 {chinese_chars} 字。请调用 audit_chapter 进行审计。",
    )
```

**中文字符计数**：用 Unicode 范围 `一-鿿` 统计 CJK 统一汉字。这是一个轻量方法，不需要额外依赖。

### 2.5 `ShortStoryStatusInfo` 增加 `next_step`

**文件**：`src/storyforge3/mcp/tools.py`（lines 82-89）

```python
class ShortStoryStatusInfo(BaseModel):
    """Short story status returned by MCP tools."""

    book_id: str = Field(description="短篇 ID")
    status: str = Field(description="状态")
    has_text: bool = Field(description="是否已有正文")
    actual_chars: int = Field(description="当前正文字符数")
    error: str | None = Field(default=None, description="错误信息")
    next_step: str | None = Field(default=None, description="建议下一步操作")
```

在 `_short_story_status_info()` 中填充：

```python
def _short_story_status_info(result) -> ShortStoryStatusInfo:
    status_val = result.status.value if hasattr(result.status, "value") else str(result.status)
    next_step = _suggest_short_story_next_step(status_val)
    return ShortStoryStatusInfo(
        book_id=result.book_id,
        status=status_val,
        has_text=bool(result.text),
        actual_chars=len(result.text),
        error=result.error,
        next_step=next_step,
    )


def _suggest_short_story_next_step(status: str) -> str | None:
    """根据短篇状态返回建议下一步操作。"""
    mapping = {
        "drafted": "短篇已起草。可调用 run_short_story 运行完整管线，或手动审计。",
        "exported": "短篇已完成并导出。",
        "failed": "短篇管线失败。请检查 error 字段，修正后重试 run_short_story。",
    }
    return mapping.get(status)
```

### 2.6 注册函数中的返回类型同步

`register_tools()` 中的 `draft_chapter` 内部函数签名需同步更新：

```python
@mcp.tool()
async def draft_chapter(book_id: str, chapter_no: int) -> DraftResult:
    """..."""  # 描述在 7C-2 中更新
    return await draft_chapter_tool(chapters, book_id, chapter_no)
```

其他 tool 的返回类型不变（`ChapterStatusInfo` 和 `AuditSummary` 和 `ShortStoryStatusInfo` 只是增加了字段，FastMCP 自动处理）。

---

## Part 3：借鉴来源

| 借鉴内容 | 来源文件 | 行数 | 借鉴方式 |
|---------|---------|------|---------|
| **结构化错误 + 建议模式** | CC-Switch `src-tauri/src/error.rs:124-146` `format_skill_error()` | ~22 行 | **模式复用**：借鉴 code + context + suggestion 三段式结构，但 SF3 用 ValueError 消息内嵌而非独立异常类 |
| **SkillError 接口** | CC-Switch `src/lib/errors/skillErrorParser.ts:6-10` `SkillError` | ~5 行 | **模式复用**：suggestion 字段概念 |
| **next_step 字段概念** | InkOS `packages/cli/src/interaction/tools.ts` | ~10 行 | **模式复用**：工具返回后建议下一步 |
| **中文字符计数** | SF3 `export/formatter.py` PlatformFormatter | — | **直接复用**：CJK Unicode 范围判断逻辑一致 |
| **状态→建议映射** | SF2 `engine/state_machine/chapter_lifecycle.py:12-17` | ~6 行 | **模式复用**：状态机状态描述 |

**新写比例**：约 **25%**。`next_step` 填充逻辑和 `DraftResult` 模型是新写的胶水代码，但核心模式（结构化错误、状态映射）全部来自 CC-Switch 和现有代码。中文字符计数直接使用标准 CJK Unicode 范围。

### 移植适配清单

| 源项目原始 | SF3 适配 |
|-----------|---------|
| CC-Switch `format_skill_error()` 返回 JSON `{code, context, suggestion}` | 不引入新异常类，在 ValueError 消息文本中内嵌建议。原因：FastMCP 对 ValueError 有原生处理，不需要自定义序列化 |
| CC-Switch `SkillError.suggestion` 独立字段 | 借鉴概念，但 SF3 在返回模型中用 `next_step: str \| None` 字段而非独立错误类 |
| InkOS 工具返回后建议 | 适配为 Pydantic `Field(default=None, description="建议下一步操作")` |

---

## 验收标准

### 错误增强

- [ ] `get_book_tool` ValueError 包含 `list_books` 和 `create_book` 建议
- [ ] `get_chapter_status_tool` ValueError 包含 `get_book` 和 `draft_chapter` 建议
- [ ] `get_short_story_status_tool` ValueError 包含 `list_books` 建议
- [ ] `get_truth_tool` ValueError 包含 `draft_chapter` → `audit_chapter` 工作流建议

### 输出增强

- [ ] `ChapterStatusInfo` 有 `next_step` 字段，7 种状态有对应建议
- [ ] `AuditSummary` 有 `next_step` 字段，通过/未通过分别有建议
- [ ] `DraftResult` 模型包含 `chapter_no` + `text` + `char_count` + `next_step`
- [ ] `draft_chapter` 返回 `DraftResult` 而非 `str`
- [ ] `ShortStoryStatusInfo` 有 `next_step` 字段
- [ ] 未知状态 `next_step` 为 `None`（优雅降级）

### 测试

- [ ] 4 个 ValueError 新消息内容有测试覆盖（match 字符串包含建议关键词）
- [ ] `_suggest_next_step()` 各状态映射有测试
- [ ] `_suggest_short_story_next_step()` 各状态映射有测试
- [ ] `draft_chapter_tool` 返回 `DraftResult`（非 `str`），包含 `char_count` 和 `next_step`
- [ ] `audit_chapter_tool` 返回 `AuditSummary` 包含 `next_step`
- [ ] 现有 432 tests 不退步

### 质量

- [ ] `ruff check .` clean
- [ ] 无新依赖引入

---

## 估算工作量

| 部分 | 文件 | 预估行数 |
|------|------|---------|
| 错误消息增强 | `mcp/tools.py`（4 处 ValueError） | ~4 行改动 |
| `DraftResult` 模型 | `mcp/tools.py` | ~8 行新增 |
| `next_step` 字段 | `mcp/tools.py`（3 个模型） | ~3 行新增 |
| `_suggest_next_step()` | `mcp/tools.py` | ~12 行新增 |
| `_suggest_short_story_next_step()` | `mcp/tools.py` | ~8 行新增 |
| `draft_chapter_tool()` 改造 | `mcp/tools.py` | ~5 行改动 |
| `audit_chapter_tool()` 改造 | `mcp/tools.py` | ~5 行改动 |
| 辅助函数更新 | `mcp/tools.py` | ~6 行改动 |
| 测试更新 | `tests/test_mcp_server.py` | ~35 行新增/改动 |
| **合计** | **2 个文件** | **~86 行** |

---

## 不做的事（Out of Scope）

- ❌ 不引入自定义 MCP 异常类（用 ValueError 消息内嵌建议即可）
- ❌ 不改 Service / Protocol 层
- ❌ 不改前端（MCP 输出变更不影响前端 API）
- ❌ 不改 `server.py`（server 配置在 7C-2 中处理）
- ❌ 不做 tool docstring 标注（7C-2 负责）
- ❌ 不做 Claude Code 注册（7C-2 负责）
