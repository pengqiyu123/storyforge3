# Phase 4 路线图：引擎深化 + API 层对齐

> 创建日期：2026-06-08
> 状态：✅ Phase 4 完成（2026-06-08）
> 📦 **时效性（2026-06-14 审核）：历史归档。** Phase 4 已完成，路线图保留作阶段背景，进度以 `../history.md` 为准。
> 前置里程碑：Phase 3 P0（3 章 E2E 全链路通过）

---

## 阶段总览

```
Phase 4A（引擎安全网）  →  Phase 4B（引擎能力）  →  Phase 4C（API 层暴露）
     ~2 天                     ~2 天                    ~5 天
```

### 决策依据

1. **引擎先行**：API 层暴露不稳定的引擎是浪费——客户端会遇到本可避免的错误
2. **安全网优先**：原子写入 + 失败持久化保护数据，为后续所有操作兜底
3. **能力后补**：Context source tracking 是 ContextPackage 的基础，API 层会消费它
4. **API 层最后**：引擎稳定后，API 对齐是一次性工作，11 个 Service Protocol 已有 Protocol 定义

---

## Phase 4A：引擎安全网（~2 天）

### 4A-1：原子写入

**问题**：`storage.write_text` 直接写入目标文件，写入中途崩溃会损坏文件。

**方案**：
- 写入临时文件（同目录，`.tmp` 后缀）
- `os.replace()` 原子移动（Windows 上也保证原子性）
- 写入前可选备份旧文件（`.bak`）

**影响范围**：
- `src/storyforge3/infrastructure/storage.py` — `write_text()` 方法
- 测试：模拟写入中途崩溃、验证备份存在

**验收标准**：
- [x] `write_text` 使用 temp+rename 模式
- [x] 崩溃后旧文件完整或新文件完整，不存在部分写入
- [x] 可选 `.bak` 备份（跳过，非必需）
- [x] 现有 266 测试全部通过 → 275 passed
- [x] 新增测试覆盖原子写入场景（5 tests）

**验收结果**（2026-06-08）：✅ 通过。`BookStorage._atomic_write_text()` 统一实现 temp+rename，`write_text` 和 `write_json` 均委托到该方法。

### 4A-2：失败时持久化中间产物

**问题**：章节在 audit 或 revise 阶段失败时，已生成的 draft/audit 结果丢失，无法 post-mortem。

**方案**：
- 每个关键步骤完成后，将中间产物写入 `diagnostics/` 目录
- 新增 `diagnostics/` 目录结构：
  ```
  books/{book_id}/diagnostics/
  ├── chapter_{n}_last_draft.md      # 最后一次 draft/revise 产物
  ├── chapter_{n}_audit.json         # 审计结果 JSON
  ├── chapter_{n}_error.txt          # 错误摘要
  └── chapter_{n}_patch.json         # patch revise 的 diff（如有）
  ```
- 失败路径（revision_exhausted, LLM error, export failure）强制写出已有产物

**影响范围**：
- `src/storyforge3/services/chapter_service.py` — draft/audit/revise 各步骤
- E2E 脚本已有部分 diagnostics 输出，需统一化

**验收标准**：
- [x] 任何失败路径都有 diagnostics 输出
- [x] draft 失败 → 保存已生成的部分文本
- [x] audit 失败 → 保存 audit JSON
- [x] revise 失败 → 保存最后一次 patch + 当前文本
- [ ] export 失败 → 保存最终文本 + truth（未单独测试，走 exception 通用路径）
- [x] 成功路径不产生多余 diagnostics（或 cleanup）

**验收结果**（2026-06-08）：✅ 通过。`ChapterWorkflow._persist_diagnostics()` 在 `_needs_review()` 中自动调用，输出 `chapter_N_last_draft.md`、`chapter_N_audit.json`、`chapter_N_error.txt`。4 个测试覆盖 revision_exhausted / exception / success / JSON-valid 路径。

---

## Phase 4B：引擎能力（~2 天）

### 4B-1：Context Source Tracking

**问题**：上下文拼装在代码中硬编码，无法追踪哪些上下文块被使用、来自哪个 source。

**方案**：
- 定义 `ContextBlock` dataclass：
  ```python
  @dataclass
  class ContextBlock:
      source: str          # "world_rules" | "character_profile" | "truth_entry" | "chapter_text" | ...
      token_count: int
      priority: int        # 0=critical, 1=high, 2=medium, 3=low
      content: str
      metadata: dict       # source-specific: character_id, chapter_no, etc.
  ```
- 定义 `ContextPackage` dataclass：
  ```python
  @dataclass
  class ContextPackage:
      blocks: list[ContextBlock]
      total_tokens: int
      budget: int | None   # max tokens allowed
      task: str            # "draft" | "audit" | "revise" | "truth_extract"
  ```
- 在 draft/audit/revise/truth 的上下文拼装处，使用 `ContextBlock` 构建 `ContextPackage`
- 预算分配：P0(critical) → P1(high) → P2(medium) → P3(low)，超预算时从 P3 开始裁剪

**影响范围**：
- 新增 `src/storyforge3/context/` 模块（`__init__.py`, `context_block.py`, `context_package.py`）
- 修改各 Service 的上下文拼装逻辑（渐进式，不强制一次性迁移）

**验收标准**：
- [x] `ContextBlock` 和 `ContextPackage` dataclass 定义
- [x] draft 步骤的上下文拼装使用 `ContextPackage`（首个迁移点）
- [x] 预算裁剪逻辑：P3 优先裁剪
- [x] `ContextPackage.to_prompt_text()` 可序列化为 LLM 输入
- [x] 新增测试覆盖预算裁剪（10 tests: 9 ContextPackage + 1 workflow 回归）
- [x] 现有 266+ 测试全部通过 → 285 passed

**验收结果**（2026-06-08）：✅ 通过。新增 `src/storyforge3/context/` 模块（3 文件），`step_draft()` 通过 `_draft_context_package()` 方法构建 ContextPackage，payload 兼容字段保留 + 新增 `context_sources` / `context_prompt` 可审计字段。渐进式迁移策略正确：只迁移 draft，其余步骤后续 Phase 迁移。

---

## Phase 4C：API 集成测试覆盖（~5 天）

> ⚠️ 路线图修正：API 路由层已于 Phase 2 完成（11 router 全挂载），无需重复建设。
> 实际缺口是 **零 API 测试覆盖**。

### 4C-1：API 集成测试

**问题**：11 个 FastAPI router 全部就位，但无任何 API 级测试。未来前端集成或重构时无安全网。

**方案**：
- 新增 `tests/conftest_api.py`（共享 fixture + dependency overrides）
- 新增 `tests/test_api_health.py`、`test_api_books.py`、`test_api_chapters.py`、`test_api_truth.py`、`test_api_export.py`、`test_api_daemon.py`
- P0: 11 个核心端点 happy-path + error-path 测试
- P1: 4 个补充测试
- 使用 `httpx.AsyncClient` + `ASGITransport`，mock LLM 依赖

**验收标准**：
- [x] P0 的 11 个 API 测试全部通过
- [x] P1 的 4 个 API 测试全部通过
- [x] 全量测试不退步 → 301 passed
- [x] ruff check clean
- [x] 确认 pytest-asyncio 配置到位（`pyproject.toml` 新增）

**验收结果**（2026-06-08）：✅ 通过。6 个测试文件 + conftest_api.py 基础设施，覆盖 11 个 router 的核心端点。使用 `httpx.AsyncClient` + `ASGITransport` + `app.dependency_overrides`，所有 LLM 依赖 mock，文件系统用 `tmp_path` 隔离。额外发现并修复 export 路由的 `FileNotFoundError`/`ValueError` 未映射为标准错误信封的 API 契约缺口。

---

## Phase 4 完成总结

**日期**：2026-06-08
**基线**：266 passed → **终态**：301 passed（+35 tests），ruff clean
**三个子阶段全部验收通过**：

| 子阶段 | 新增测试 | 核心交付 |
|--------|----------|----------|
| 4A 原子写入 + 失败持久化 | +9 | `BookStorage._atomic_write_text()` + `_persist_diagnostics()` |
| 4B Context Source Tracking | +10 | `ContextBlock`/`ContextPackage`/`ContextPriority` + draft 迁移 |
| 4C API 集成测试 | +16 | 6 测试文件 + conftest + export 路由修复 |

---

## 未来阶段（Phase 5+）

以下不在 Phase 4 范围内，记录备忘：

| 阶段 | 功能 | 依据 |
|------|------|------|
| Phase 5A | React 前端 | `docs/research/剩余功能评估.md` 方案 B |
| Phase 5B | 短篇管线 | InkOS 7阶段简化为5阶段 |
| Phase 5C | 通知渠道 | Telegram/飞书/企微 Webhook |
| Phase 5D | 同人模式 | canon 导入 + 4 模式审计 |
| Phase 5E | JSONL 审计日志 | 可审计性 |
| Phase 5F | 历史 Snapshot / Zip 备份 | 数据安全 |

---

## 文件变更清单（实际）

### Phase 4A
| 文件 | 改动类型 |
|------|----------|
| `src/storyforge3/storage.py` | 修改：`write_text` / `write_json` 改为 temp+rename 原子写入 |
| `src/storyforge3/workflow.py` | 修改：`_needs_review()` 失败路径写 diagnostics |
| `tests/test_storage_atomic.py` | 新增：原子写入测试 |
| `tests/test_workflow_diagnostics.py` | 新增：失败产物持久化测试 |

### Phase 4B
| 文件 | 改动类型 |
|------|----------|
| `src/storyforge3/context/__init__.py` | 新增 |
| `src/storyforge3/context/context_block.py` | 新增：ContextBlock dataclass |
| `src/storyforge3/context/context_package.py` | 新增：ContextPackage + 预算裁剪 |
| `src/storyforge3/workflow.py` | 修改：draft 用 ContextPackage |
| `tests/test_context_package.py` | 新增 |
| `tests/test_workflow.py` | 修改：draft payload source summary 回归测试 |

### Phase 4C
| 文件 | 改动类型 |
|------|----------|
| `tests/conftest_api.py` | 新增：共享 fixture + dependency overrides |
| `tests/test_api_health.py` | 新增：health + providers 测试 |
| `tests/test_api_books.py` | 新增：books CRUD 测试 |
| `tests/test_api_chapters.py` | 新增：chapters pipeline 测试 |
| `tests/test_api_truth.py` | 新增：truth read + extract 测试 |
| `tests/test_api_export.py` | 新增：export 错误信封测试 |
| `tests/test_api_daemon.py` | 新增：daemon start 测试 |
| `tests/conftest.py` | 修改：加载 `tests.conftest_api` |
| `src/storyforge3/api/routes/export.py` | 修改：export 错误映射为标准 API 信封 |
| `src/storyforge3/services/export_service.py` | 修改：缺失书籍 fail fast |
| `tests/test_export_service.py` | 修改：缺失书籍导出回归测试 |
| `pyproject.toml` | 修改：新增 `pytest-asyncio` dev 依赖和 `asyncio_mode=auto` |

---

## 执行节奏

```
Day 1-2: Phase 4A（原子写入 + 失败持久化）
         Codex 独立完成，PM 验收

Day 3-4: Phase 4B（Context source tracking）
         Codex 独立完成，PM 验收

Day 5-9: Phase 4C（API 集成测试覆盖）
         Codex 完成 P0 的 11 个 API 测试 + P1 的 4 个测试
         PM 逐个验收
```
