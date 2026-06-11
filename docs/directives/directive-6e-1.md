# Codex 指令：Phase 6E-1 — MCP Server 基础框架

> 发出日期：2026-06-09
> 产品经理：Claude Code PM
> 执行者：Codex
> 前置条件：Phase 6B-2 完成（374 后端 tests, 39 前端 tests, ruff clean）

---

## 任务概述

为 StoryForge3 搭建 MCP（Model Context Protocol）Server，让外部 AI 工具（Claude Code、Codex）通过 MCP 协议调用 SF3 的核心创作能力。

**本阶段范围**：基础框架 + 5 个核心 tool + STDIO transport + 不依赖前端的测试闭环。6E-2 再扩展更多 tool。

**核心原则**：

1. 使用 Python MCP SDK（`mcp` 包）的 `FastMCP` 高层 API
2. 复用现有 StoryForge3 服务（BookService/ChapterService/ExportService），MCP Server 是薄封装层
3. STDIO transport（本地进程通信），不搞 HTTP/SSE
4. 每个 tool 调用真实的 SF3 服务方法，不 mock 业务逻辑

---

## 技术选型

### Python MCP SDK

```
包名：mcp
安装：pip install "mcp[cli]"
版本：≥ 1.20
依赖：自动安装（uv, httpx, pydantic 等）
```

**参考**：Letta workspace 中的 `mock_mcp_server.py` 使用相同模式。

### FastMCP 核心模式

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("StoryForge")

@mcp.tool()
async def list_books() -> list[dict]:
    """List all books in the workspace."""
    ...

mcp.run(transport="stdio")  # 入口
```

- 工具参数：Python type hints 自动生成 JSON Schema
- 工具描述：docstring 展示给 AI 客户端
- 返回值：Pydantic model → structuredContent + text 双通道
- 错误：`raise ValueError(...)` → FastMCP 自动包装为 `isError=True`

---

## 文件结构

```
src/storyforge3/mcp/
├── __init__.py           # 模块入口，导出 create_server
├── server.py             # FastMCP 实例创建 + 服务组装
└── tools.py              # 5 个 tool 定义
```

### 为什么是独立模块（不是 api/ 下）

- MCP Server 是独立进程（STDIO 通信），不走 FastAPI
- MCP Server 有自己的依赖注入（一次性组装服务，不像 HTTP 请求级 DI）
- 未来可能独立打包

---

## 功能 1：服务组装

### 1.1 `src/storyforge3/mcp/server.py`（新建，~60 行）

```python
from mcp.server.fastmcp import FastMCP
from storyforge3.config import StoryForge3Config
from storyforge3.services.book_service import BookService
from storyforge3.services.chapter_service import ChapterService
from storyforge3.services.export_service import ExportService
from storyforge3.storage import BookStorage, StoragePaths

def create_server() -> FastMCP:
    """创建 MCP Server 实例并组装依赖。"""
    config = StoryForge3Config()
    paths = StoragePaths(Path(config.books_dir))
    storage = BookStorage(paths.books_root)

    book_service = BookService(storage, paths)
    chapter_service = ChapterService(config)
    export_service = ExportService(storage, paths)

    mcp = FastMCP(
        "StoryForge",
        instructions="StoryForge3 网文创作引擎。提供书籍管理、章节起草、审计和导出能力。"
    )

    # 把 services 注入到 tool 函数中
    # 方案：用闭包捕获 services（与 Letta mock_mcp_server 一致）
    from storyforge3.mcp.tools import register_tools
    register_tools(mcp, book_service, chapter_service, export_service)

    return mcp
```

**关键设计**：服务在 `create_server()` 时一次性创建，整个 MCP Server 生命周期共享。不走 FastAPI 的请求级 DI。

---

## 功能 2：5 个核心 Tool

### 2.1 `src/storyforge3/mcp/tools.py`（新建，~200 行）

```python
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field
from mcp.server.fastmcp import FastMCP

from storyforge3.services.book_service import BookService
from storyforge3.services.chapter_service import ChapterService
from storyforge3.services.export_service import ExportService


# ── Pydantic 输出模型 ──────────────────────────────────────────

class BookInfo(BaseModel):
    book_id: str = Field(description="书籍 ID")
    title: str = Field(description="书名")
    genre: str = Field(description="类型")
    status: str = Field(description="状态")
    current_chapter: int = Field(description="当前章节数")
    target_chapters: int = Field(description="目标章节数")

class AuditSummary(BaseModel):
    chapter_no: int = Field(description="章节号")
    passed: bool = Field(description="是否通过")
    blocking_count: int = Field(description="阻断性问题数")
    warning_count: int = Field(description="警告数")

class ExportResult(BaseModel):
    path: str = Field(description="导出文件路径")
    format: str = Field(description="导出格式")


# ── Tool 注册 ──────────────────────────────────────────────

def register_tools(
    mcp: FastMCP,
    books: BookService,
    chapters: ChapterService,
    exports: ExportService,
) -> None:
    """注册 5 个核心 MCP tool。"""

    @mcp.tool()
    async def list_books() -> list[BookInfo]:
        """列出工作区中的所有书籍。

        返回每本书的 ID、标题、类型、状态和进度信息。
        """
        book_list = await books.list_books()
        return [
            BookInfo(
                book_id=b.book_id,
                title=b.title,
                genre=b.genre,
                status=b.status.value,
                current_chapter=b.current_chapter,
                target_chapters=b.target_chapters,
            )
            for b in book_list
        ]

    @mcp.tool()
    async def get_book(book_id: str) -> BookInfo:
        """获取指定书籍的详细信息。

        Args:
            book_id: 书籍 ID（从 list_books 获取）
        """
        meta = await books.get(book_id)
        if meta is None:
            raise ValueError(f"书籍不存在: {book_id}")
        return BookInfo(
            book_id=meta.book_id,
            title=meta.title,
            genre=meta.genre,
            status=meta.status.value,
            current_chapter=meta.current_chapter,
            target_chapters=meta.target_chapters,
        )

    @mcp.tool()
    async def draft_chapter(
        book_id: str,
        chapter_no: int,
    ) -> str:
        """为指定书籍起草一章。

        完整流程：自动规划 → 起草 → 返回正文。
        注意：此操作可能需要几分钟（LLM 生成）。

        Args:
            book_id: 书籍 ID
            chapter_no: 章节号（从 1 开始）
        """
        # 先规划（如果还没规划）
        intent = await chapters.plan(book_id, chapter_no)
        # 起草
        text = await chapters.draft(book_id, chapter_no, intent)
        return text

    @mcp.tool()
    async def audit_chapter(
        book_id: str,
        chapter_no: int,
    ) -> AuditSummary:
        """审计指定章节。

        运行 36 条机械规则 + LLM 4 维度审计。
        注意：LLM 审计可能需要几十秒。

        Args:
            book_id: 书籍 ID
            chapter_no: 章节号
        """
        result = await chapters.audit(book_id, chapter_no)
        return AuditSummary(
            chapter_no=result.chapter_no,
            passed=result.passed,
            blocking_count=len(result.blocking_issues),
            warning_count=len(result.warnings),
        )

    @mcp.tool()
    async def export_book(
        book_id: str,
        fmt: Literal["tomato_txt", "md", "epub", "qidian_txt"] = "tomato_txt",
    ) -> ExportResult:
        """导出整本书为指定格式。

        Args:
            book_id: 书籍 ID
            fmt: 导出格式（tomato_txt / md / epub / qidian_txt）
        """
        path = await exports.export_book(book_id, fmt)
        return ExportResult(path=str(path), format=fmt)
```

**设计要点**：

1. **Pydantic 输出模型**：`BookInfo` / `AuditSummary` / `ExportResult`。FastMCP 自动生成 structuredContent + text 双通道输出。
2. **`draft_chapter` 调用 plan + draft**：MCP 客户端（如 Claude Code）不需要理解 SF3 内部的 plan→draft 分步流程，一个 tool 调用搞定。
3. **`audit_chapter` 调用 `chapters.audit()`**：复用现有 36 机械规则 + LLM 4 维度。
4. **错误处理**：`raise ValueError(...)` → FastMCP 自动包装为 `isError=True`。简单直接。
5. **闭包捕获 services**：`register_tools()` 接收 services 实例，tool 函数通过闭包引用。不需要全局状态。

---

## 功能 3：CLI 入口

### 3.1 在 `cli.py` 中添加 `mcp` 命令

在现有的 `storyforge3` CLI 中添加一个 `mcp` 子命令：

```python
@app.command()
def mcp() -> None:
    """启动 MCP Server（STDIO 模式）。"""
    from storyforge3.mcp.server import create_server
    server = create_server()
    server.run(transport="stdio")
```

或者，提供独立入口（方便 `claude mcp add` 注册）：

### 3.2 `src/storyforge3/mcp/__main__.py`（新建，~10 行）

```python
"""StoryForge MCP Server 独立入口。

用法:
    python -m storyforge3.mcp

注册到 Claude Code:
    claude mcp add storyforge -- python -m storyforge3.mcp
"""
from storyforge3.mcp.server import create_server

def main() -> None:
    server = create_server()
    server.run(transport="stdio")

if __name__ == "__main__":
    main()
```

**两种运行方式**：
- `storyforge3 mcp`（通过现有 CLI）
- `python -m storyforge3.mcp`（独立入口，用于 MCP 客户端注册）

---

## 功能 4：依赖管理

### 4.1 `pyproject.toml` 添加依赖

```toml
[project.optional-dependencies]
mcp = ["mcp[cli]>=1.20"]
```

或者直接加到主依赖（因为 MCP 是核心功能不是可选的）：

```toml
dependencies = [
    # ... 现有依赖 ...
    "mcp>=1.20",
]
```

**推荐**：直接加到主依赖。MCP Server 是 SF3 的核心输出之一，不应是可选的。

---

## 测试

### 测试策略

MCP Server 的测试不需要真正的 MCP 客户端。FastMCP 提供了 `ClientSession` 测试工具。

### 4.1 `tests/test_mcp_server.py`（新建，~120 行）

```python
"""MCP Server 测试：验证 5 个核心 tool 的注册和调用。"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from storyforge3.models import BookMeta, BookStatus, AuditResult, RuleResult

# 测试方式：直接调用 tool 函数（通过 FastMCP 的 test client）

@pytest.fixture
def mock_services():
    """创建 mock services。"""
    books = AsyncMock(spec=BookService)
    chapters = AsyncMock(spec=ChapterService)
    exports = AsyncMock(spec=ExportService)
    return books, chapters, exports

@pytest.fixture
def mcp_server(mock_services):
    """创建带 mock services 的 MCP server。"""
    from storyforge3.mcp.server import create_server
    # 或者直接构建
    ...

# 测试要点
def test_list_books_returns_book_infos(mock_services):
    """list_books 返回 BookInfo 列表。"""
    ...

def test_list_books_empty_workspace(mock_services):
    """空工作区返回空列表。"""
    ...

def test_get_book_existing(mock_services):
    """获取存在的书籍返回完整信息。"""
    ...

def test_get_book_not_found(mock_services):
    """不存在的书籍抛出 ValueError。"""
    ...

async def test_draft_chapter_calls_plan_and_draft(mock_services):
    """draft_chapter 调用 plan + draft。"""
    ...

async def test_audit_chapter_returns_summary(mock_services):
    """audit_chapter 返回 AuditSummary。"""
    ...

async def test_export_book_returns_path(mock_services):
    """export_book 返回 ExportResult。"""
    ...

async def test_export_book_unsupported_format(mock_services):
    """不支持的格式返回错误。"""
    ...
```

### 4.2 测试方式说明

FastMCP 的测试推荐两种方式：

**方式 A：直接调用注册的 tool 函数**

创建 server 后，tool 函数是闭包，不太好直接调用。

**方式 B：使用 FastMCP 的 test client**

```python
# FastMCP 没有 built-in test client，但可以模拟 STDIO 通信
# 或者直接测试 tool 的逻辑（提取为独立函数）
```

**推荐方案**：将 tool 的核心逻辑提取为可测试的独立函数，tool 函数只做参数解包和调用。

```python
# tools.py 中的 tool 函数很薄（1-3 行），核心逻辑在 services 中
# 测试重点：
# 1. Tool 参数解析是否正确（Pydantic model → service 参数）
# 2. 错误映射是否正确（service 异常 → MCP 错误）
# 3. 输出格式是否正确（service 返回值 → Pydantic model）
```

实际上，由于 tool 函数只是 services 的薄封装（每层 1-3 行代码），测试重点在：

1. **`register_tools` 不抛异常**：验证 5 个 tool 成功注册
2. **参数映射正确**：mock services → 调用 tool → 验证 services 被正确调用
3. **错误处理**：`get_book` 不存在时返回 `isError=True`

---

## 文件改动清单

### 新增（~300 行）

| 文件 | 行数 | 说明 |
|------|------|------|
| `src/storyforge3/mcp/__init__.py` | ~5 | 模块入口 |
| `src/storyforge3/mcp/__main__.py` | ~10 | 独立 CLI 入口 |
| `src/storyforge3/mcp/server.py` | ~50 | FastMCP 实例 + 服务组装 |
| `src/storyforge3/mcp/tools.py` | ~150 | 5 个 tool 定义 + Pydantic 模型 |
| `tests/test_mcp_server.py` | ~120 | 5 个 tool 测试 |

### 修改

| 文件 | 说明 |
|------|------|
| `pyproject.toml` | 添加 `mcp>=1.20` 依赖 |
| `src/storyforge3/cli.py` | 添加 `mcp` 子命令 |

---

## 复用清单

| 组件 | 来源 | 复用方式 |
|------|------|---------|
| `BookService` | services/book_service.py | `list_books()` + `get()` |
| `ChapterService` | services/chapter_service.py | `plan()` + `draft()` + `audit()` |
| `ExportService` | services/export_service.py | `export_book()` |
| `StoryForge3Config` | config.py | 服务实例化 |
| `FastMCP` 模式 | Letta mock_mcp_server.py | `@mcp.tool()` + `mcp.run()` |

**不修改的现有文件**（除了 pyproject.toml/cli.py 的小幅扩展外）：
- 所有 service 文件 — 不动
- 所有 model 文件 — 不动
- 所有 API 路由 — 不动

---

## 验收标准

### Tool 注册

- [ ] 5 个 tool 全部注册：list_books / get_book / draft_chapter / audit_chapter / export_book
- [ ] 每个 tool 有清晰的中文 docstring
- [ ] 参数 JSON Schema 自动生成正确

### Tool 行为

- [ ] `list_books()` 返回工作区所有书籍的 BookInfo 列表
- [ ] `get_book(book_id)` 返回单本书详情，不存在时返回错误
- [ ] `draft_chapter(book_id, chapter_no)` 调用 plan + draft，返回正文
- [ ] `audit_chapter(book_id, chapter_no)` 调用 audit，返回 AuditSummary
- [ ] `export_book(book_id, fmt)` 调用 export_book，返回文件路径

### 运行

- [ ] `python -m storyforge3.mcp` 能启动（STDIO 模式，不报错）
- [ ] `storyforge3 mcp` CLI 命令能启动
- [ ] 启动时不触发 LLM 调用（服务组装只创建实例，不调用 API）

### 隔离性

- [ ] 374 后端 tests 不退步
- [ ] 39 前端 tests 不退步
- [ ] ruff check clean
- [ ] 现有 service/model/API 零改动

### 测试

- [ ] 新增 ~8 个 MCP 测试
- [ ] 测试通过 mock services 验证 tool 行为，不依赖真实 LLM
- [ ] pytest 全量 382+ tests passed

---

## 不在 6E-1 范围内

| 功能 | 归属 | 原因 |
|------|------|------|
| SSE/HTTP transport | 6E-2 | 先跑通 STDIO |
| 更多 tool（world/character/truth/short_story） | 6E-2 | 先验证 5 个核心 |
| 认证/Token | 6E-2 | STDIO 本地通信不需要 |
| Claude Code 注册脚本 | 6E-2 | 框架稳定后 |
| 长时间运行的进度报告 | 6E-2 | 先做基本功能 |

---

## 参考文件

### 必须读取

1. **`src/storyforge3/services/book_service.py`** — list_books / get 签名
2. **`src/storyforge3/services/chapter_service.py`** — plan / draft / audit 签名
3. **`src/storyforge3/services/export_service.py`** — export_chapter / export_book 签名
4. **`src/storyforge3/config.py`** — StoryForge3Config + 服务实例化
5. **`src/storyforge3/cli.py`** — 现有 CLI 命令注册模式
6. **`pyproject.toml`** — 现有依赖列表

### 外部参考

7. **MCP Python SDK**: `pip install "mcp[cli]"`，使用 `FastMCP` + `@mcp.tool()` + `mcp.run(transport="stdio")`
8. **Letta mock_mcp_server.py**: `storyforge/process/ai-company-sources/letta/tests/mock_mcp_server.py` — FastMCP 用法参考

---

## 完成后回报格式

```
给 ClaudeCode 产品经理的执行结果：

Phase 6E-1（MCP Server 基础框架）：

框架搭建：
- FastMCP 实例：[状态]
- 服务组装：[状态 + 方式]
- CLI 入口：[状态 + 命令]
- 依赖添加：[状态 + 版本]

Tool 注册：
- list_books：[状态 + 返回类型]
- get_book：[状态 + 参数 + 错误处理]
- draft_chapter：[状态 + 调用了哪些 service 方法]
- audit_chapter：[状态 + 返回类型]
- export_book：[状态 + 支持格式]

运行验证：
- python -m storyforge3.mcp：[状态]
- storyforge3 mcp：[状态]

测试：
- 新增 MCP 测试：[数量] passed
- 后端全量：[数量] passed
- 前端：[数量] passed
- ruff check：[状态]

改动文件列表：[...]
```
