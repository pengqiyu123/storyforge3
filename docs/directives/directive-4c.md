# Codex 指令：Phase 4C — API 集成测试覆盖

> 发出日期：2026-06-08
> 产品经理：Claude Code PM
> 执行者：Codex
> 前置条件：Phase 4A + 4B 已通过

---

## 任务概述

API 路由层已完成（11 个 router 挂载到 `app.py`），但 **零测试覆盖**。本任务补全 API 集成测试，确保每个端点有至少 1 个 happy-path 测试 + 关键 error-path 测试。

---

## 背景

当前路由清单（全部已挂载）：

| Router | Prefix | 关键端点 |
|--------|--------|----------|
| health | `/api` | `GET /api/health` |
| books | `/api/books` | `POST` (create), `GET` (list), `GET /{id}`, `PATCH /{id}/status` |
| world | `/api/books/{id}/world` | world CRUD |
| characters | `/api/books/{id}/characters` | characters CRUD |
| volumes | `/api/books/{id}/volumes` | volumes CRUD |
| chapters | `/api/books/{id}/chapters` | `POST /{n}/plan`, `draft`, `audit`, `llm-audit`, `normalize`, `revise`, `approve`, `export`, `run`, `GET /{n}/status` |
| truth | `/api/books/{id}/truth` | `GET /latest`, `GET /{n}`, `POST /extract` |
| export | `/api/books/{id}` | `POST /export`, `GET /exports/{filename}` |
| providers | `/api/providers` | `GET` (list), `GET /health` |
| daemon | `/api/books/{id}/daemon` | `POST /start` |
| events | `/api` | SSE `/api/events` |

响应信封格式：
```json
{
  "ok": true,
  "data": { ... },
  "error": null
}
```

错误信封：
```json
{
  "ok": false,
  "data": null,
  "error": { "code": "BOOK_NOT_FOUND", "message": "..." }
}
```

---

## 修改目标

### 1. 新增 conftest fixture（共享测试基础设施）

新增 `tests/conftest_api.py`，提供：

```python
import pytest
from httpx import AsyncClient, ASGITransport
from storyforge3.api.app import app

@pytest.fixture
async def client():
    """Async test client for FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

**关键**：需要 override deps 中的 service 依赖，避免调用真实 LLM。使用 FastAPI 的 `app.dependency_overrides` 模式。

### 2. 测试文件结构

```
tests/
├── conftest_api.py              # 共享 fixture + dependency overrides
├── test_api_health.py           # health + providers
├── test_api_books.py            # books CRUD
├── test_api_chapters.py         # chapters pipeline endpoints
├── test_api_truth.py            # truth read + extract
├── test_api_export.py           # export + download
└── test_api_daemon.py           # daemon start
```

### 3. 优先级 P0 测试（必须完成）

以下端点必须有 happy-path 测试：

| # | 测试文件 | 测试名 | 覆盖端点 |
|---|----------|--------|----------|
| 1 | `test_api_health.py` | `test_health_returns_ok` | `GET /api/health` |
| 2 | `test_api_books.py` | `test_create_book_returns_id` | `POST /api/books` |
| 3 | `test_api_books.py` | `test_list_books_returns_array` | `GET /api/books` |
| 4 | `test_api_books.py` | `test_get_book_not_found` | `GET /api/books/{id}` → 404 |
| 5 | `test_api_chapters.py` | `test_audit_returns_result` | `POST /api/books/{id}/chapters/{n}/audit` |
| 6 | `test_api_chapters.py` | `test_audit_chapter_not_found` | `POST` 不存在的 chapter → 404 |
| 7 | `test_api_chapters.py` | `test_normalize_validates_input` | `POST normalize` target_chars=0 → 400 |
| 8 | `test_api_chapters.py` | `test_get_status_not_found` | `GET status` 不存在 → 404 |
| 9 | `test_api_truth.py` | `test_get_latest_truth_empty` | `GET /api/books/{id}/truth/latest` → data=null |
| 10 | `test_api_export.py` | `test_export_book_not_found` | `POST /api/books/{id}/export` → 404 |
| 11 | `test_api_daemon.py` | `test_start_daemon_returns_started` | `POST /api/books/{id}/daemon/start` |

### 4. 优先级 P1 测试（尽量完成）

| # | 测试文件 | 测试名 | 覆盖端点 |
|---|----------|--------|----------|
| 12 | `test_api_books.py` | `test_update_book_status` | `PATCH /api/books/{id}/status` |
| 13 | `test_api_chapters.py` | `test_revise_invalid_mode` | `POST revise` mode=bad → 400 |
| 14 | `test_api_truth.py` | `test_extract_truth_success` | `POST /api/books/{id}/truth/extract` |
| 15 | `test_api_providers.py` | `test_list_providers` | `GET /api/providers` |

### 5. Dependency Override 策略

核心原则：**不调用真实 LLM**。所有 LLM 相关依赖替换为 mock：

```python
from unittest.mock import AsyncMock

# 在 conftest_api.py 中
def _mock_llm_service():
    mock = AsyncMock()
    mock.check_health = AsyncMock(return_value=True)
    mock.generate_text = AsyncMock(return_value="测试文本。")
    mock.generate_json = AsyncMock(return_value={"patches": []})
    mock.last_call = None
    return mock

def _mock_book_service():
    """返回一个使用 tmp_path 的 BookService，不触碰真实数据。"""
    ...
```

对于 **不依赖 LLM** 的端点（audit、health、list books、get truth），可以使用真实 service + `tmp_path` fixture：

```python
@pytest.fixture
def tmp_books_dir(tmp_path):
    """提供隔离的 books 目录。"""
    return tmp_path / "books"
```

对于 **依赖 LLM** 的端点（draft、revise、plan、extract truth），必须 mock LLM service。

---

## 技术约束

1. 使用 `httpx.AsyncClient` + `ASGITransport`（FastAPI 官方推荐测试方式）
2. 所有测试 `@pytest.mark.asyncio`
3. 测试之间独立，不依赖执行顺序
4. 使用 `tmp_path` fixture 隔离文件系统
5. 不需要 `pytest.ini` 配置（项目已有 `pyproject.toml` pytest 配置）

### 检查现有 pytest 配置

先确认 `pyproject.toml` 中是否有 `asyncio_mode` 配置。如果没有，需添加：

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

并确认 `pytest-asyncio` 在 dev dependencies 中。

---

## 验收

```powershell
ruff check tests/test_api_*.py tests/conftest_api.py
.\.venv\Scripts\python.exe -m pytest tests/test_api_*.py -v
.\.venv\Scripts\python.exe -m pytest -q   # 全量测试不退步
```

最低要求：P0 的 11 个测试全部通过。
目标：P0 + P1 共 15 个测试全部通过。

---

## 完成后回报格式

```
给 ClaudeCode 产品经理的执行结果：

Phase 4C（API 集成测试覆盖）：
- P0 测试：N/11 passed
- P1 测试：N/4 passed
- 新增测试文件数：N
- 新增 fixture 文件：conftest_api.py [是/否]
- 全量测试：N passed
- ruff check：[clean / 有 warnings]
- pytest-asyncio 配置：[已有 / 新增]
```
