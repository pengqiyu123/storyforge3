# Codex 指令：Phase 5C-2 — Service 架构对齐

> 发出日期：2026-06-08
> 产品经理：Claude Code PM
> 执行者：Codex
> 前置条件：Phase 5C-1 完成（310 tests, ruff clean, PipelineLogger 模块已就位）

---

## 任务概述

为 4 个缺失的 Protocol 创建 Service 实现。每个 Service 是现有模块功能的薄封装（Facade），不引入新业务逻辑。

**目标**：所有 11 个 Service Protocol 均有对应实现，可通过 deps.py 注入。

---

## 当前状态

### 已有 Protocol 与实现对照

| Protocol | 实现 | deps.py | 状态 |
|----------|------|---------|------|
| LLMServiceProtocol | `create_llm_service()` | ✅ | 完成 |
| BookServiceProtocol | `BookService` | ✅ | 完成 |
| WorldServiceProtocol | `WorldService` | ✅ | 完成 |
| CharacterServiceProtocol | `CharacterService` | ✅ | 完成 |
| VolumeServiceProtocol | `VolumeService` | ✅ | 完成 |
| ChapterServiceProtocol | `ChapterService` | ✅ | 完成 |
| ExportServiceProtocol | `ExportService` | ✅ | 完成 |
| DaemonServiceProtocol | `DaemonService` | ✅ | 完成 |
| **AuditServiceProtocol** | ❌ 无 | ❌ | **缺失** |
| **TruthServiceProtocol** | ❌ 无 | ❌ | **缺失** |
| **PromptServiceProtocol** | ❌ 无 | ❌ | **缺失** |
| **StyleServiceProtocol** | ❌ 无 | ❌ | **缺失** |

### 现有功能模块（待封装）

| 模块 | 位置 | 核心类/方法 |
|------|------|-------------|
| 机械审计 | `audit/runner.py` | `AuditRunner.run_audit(chapter_no, text) -> AuditResult` |
| LLM 审计 | `audit/llm_auditor.py` | `LLMAuditor.audit(chapter_text, characters, world, previous_truth) -> LLMAuditResult` |
| Truth 提取 | `truth/extractor.py` | `TruthExtractor.extract(chapter_no, chapter_text, previous_truth) -> TruthData` |
| Truth 存储 | `truth/store.py` | `TruthStore.save()` / `load()` / `load_latest()` / `detect_gaps()` |
| Prompt 管理 | `prompts/registry.py` | `PromptRegistry.register()` / `get_latest()` / `render_system_prompt()` / `list_task_types()` |
| Style 契约 | `style/contract.py` | `StyleContract` (frozen dataclass) + `DEFAULT_STYLE_CONTRACT` |
| Style 检查 | `style/guard.py` | `StyleGuard.check(text) -> StyleGuardReport` |

---

## 修改目标

### 1. AuditService

**文件**：`src/storyforge3/services/audit_service.py`（新建）

封装 `AuditRunner` 和 `LLMAuditor`。

```python
from __future__ import annotations

from storyforge3.audit.llm_auditor import LLMAuditor, LLMAuditResult
from storyforge3.audit.runner import AuditRunner
from storyforge3.config import StoryForge3Config
from storyforge3.llm.factory import create_llm_service
from storyforge3.models import AuditResult
from storyforge3.prompts.registry import PromptRegistry, create_default_registry
from storyforge3.style.contract import DEFAULT_STYLE_CONTRACT, StyleContract


class AuditService:
    """质量审计服务：机械规则 + LLM 4 维度审计。"""

    def __init__(
        self,
        *,
        config: StoryForge3Config,
        audit_runner: AuditRunner | None = None,
        llm_auditor: LLMAuditor | None = None,
        registry: PromptRegistry | None = None,
        style_contract: StyleContract | None = None,
    ) -> None:
        self.config = config
        self._runner = audit_runner or AuditRunner(style_contract)
        self._registry = registry or create_default_registry()
        self._llm = llm_auditor  # lazy: only created when needed

    def run_mechanical(self, chapter_no: int, text: str) -> AuditResult:
        """运行 36 条机械审计规则。"""
        return self._runner.run_audit(chapter_no, text)

    async def run_llm_audit(
        self,
        text: str,
        context: str,
        *,
        model: str | None = None,
    ) -> LLMAuditResult:
        """运行 LLM 4 维度审计（OOC、战力一致性、信息边界、情节逻辑）。

        context 参数包含 world/characters/previous_truth 的文本摘要，
        由调用方准备并传入。
        """
        auditor = self._llm_auditor
        if auditor is None:
            from storyforge3.llm.factory import create_llm_service
            auditor = LLMAuditor(create_llm_service(self.config), self._registry, self.config)
        # context 在 Protocol 层是 str，LLMAuditor 需要 characters/world/previous_truth
        # 这里简化为只传 chapter_text，具体展开由调用方负责
        return await auditor.audit(chapter_text=text, characters=(), world=None, previous_truth=None)
```

**注意**：`AuditServiceProtocol.run_llm_audit` 签名是 `(text, context, *, model) -> AuditResult`，
但实际 `LLMAuditor.audit()` 返回 `LLMAuditResult` 且签名不同。Service 做适配：
- Protocol 返回类型改为 `LLMAuditResult`（这是合理的，因为 Protocol 定义在前，实现修正返回类型）
- 如果严格匹配 Protocol，需要转换。**选方案**：Protocol 返回类型保持 `AuditResult`，Service 内部将 `LLMAuditResult` 转为 `AuditResult`（提取 passed + issues 映射）。

**最终选择**：直接返回 `LLMAuditResult`，**同时更新 Protocol 的返回类型**为 `LLMAuditResult`。这更准确——机械审计返回 `AuditResult`，LLM 审计返回 `LLMAuditResult`，它们是不同的审计维度。

### 2. TruthService

**文件**：`src/storyforge3/services/truth_service.py`（新建）

封装 `TruthExtractor` + `TruthStore`。

```python
from __future__ import annotations

from storyforge3.config import StoryForge3Config
from storyforge3.models import TruthData
from storyforge3.prompts.registry import PromptRegistry, create_default_registry
from storyforge3.truth.extractor import TruthExtractor
from storyforge3.truth.store import TruthStore


class TruthService:
    """Truth 提取、存储、查询的统一服务。"""

    def __init__(
        self,
        *,
        config: StoryForge3Config,
        extractor: TruthExtractor | None = None,
        store: TruthStore | None = None,
        registry: PromptRegistry | None = None,
    ) -> None:
        self.config = config
        self._store = store or TruthStore(config.books_dir)
        registry = registry or create_default_registry()
        self._extractor = extractor or TruthExtractor(
            # lazy: extractor needs LLM client, defer to first call
            None,  # placeholder, will be set in extract()
            registry,
        )

    async def extract(
        self,
        chapter_no: int,
        text: str,
        prev: TruthData | None = None,
    ) -> TruthData:
        """从章节文本提取 truth 条目。Fail-closed。"""
        if self._extractor is None or getattr(self._extractor, '_client', None) is None:
            from storyforge3.llm.factory import create_llm_service
            self._extractor = TruthExtractor(create_llm_service(self.config), self._registry)
        return await self._extractor.extract(chapter_no, text, prev)

    def save(self, book_id: str, truth: TruthData) -> None:
        """持久化 truth 数据。"""
        self._store.save(book_id, truth)

    def load_latest(self, book_id: str) -> TruthData | None:
        """加载最新的 truth 数据。"""
        return self._store.load_latest(book_id)

    def load_history(self, book_id: str) -> list[TruthData]:
        """加载所有章节的 truth 历史。"""
        results: list[TruthData] = []
        chapter = 1
        while True:
            truth = self._store.load(book_id, chapter)
            if truth is None:
                break
            results.append(truth)
            chapter += 1
        return results
```

### 3. PromptService

**文件**：`src/storyforge3/services/prompt_service.py`（新建）

封装 `PromptRegistry`。

```python
from __future__ import annotations

from storyforge3.prompts.registry import PromptRegistry, PromptTemplate, create_default_registry


class PromptService:
    """版本化 Prompt 模板管理服务。"""

    def __init__(self, registry: PromptRegistry | None = None) -> None:
        self._registry = registry or create_default_registry()

    def get(self, task_type: str, version: int | None = None) -> PromptTemplate:
        """获取指定任务类型的模板。version=None 取最新。"""
        if version is None:
            return self._registry.get_latest(task_type)
        return self._registry.get_version(task_type, version)

    def render(self, task_type: str, **kwargs: object) -> str:
        """渲染系统提示词。"""
        template = self._registry.get_latest(task_type)
        return self._registry.render_system_prompt(template, **kwargs)

    def list_templates(self) -> list[dict]:
        """列出所有已注册的任务类型及其版本。"""
        return [
            {"task_type": task_type, "versions": self._registry.list_versions(task_type)}
            for task_type in self._registry.list_task_types()
        ]
```

### 4. StyleService

**文件**：`src/storyforge3/services/style_service.py`（新建）

封装 `StyleContract` + `StyleGuard` + book.json 持久化。

```python
from __future__ import annotations

import json
from pathlib import Path

from storyforge3.config import StoryForge3Config
from storyforge3.style.contract import DEFAULT_STYLE_CONTRACT, StyleContract
from storyforge3.style.guard import StyleGuard, StyleGuardReport


class StyleService:
    """风格契约与合规检查服务。"""

    def __init__(self, config: StoryForge3Config) -> None:
        self._books_dir = config.books_dir

    def get_contract(self, book_id: str) -> StyleContract:
        """获取书籍的风格契约。未配置则返回默认契约。"""
        path = Path(self._books_dir) / book_id / "book.json"
        if not path.exists():
            return DEFAULT_STYLE_CONTRACT
        data = json.loads(path.read_text(encoding="utf-8"))
        contract_data = data.get("style_contract")
        if not isinstance(contract_data, dict):
            return DEFAULT_STYLE_CONTRACT
        try:
            return StyleContract(
                contract_id=contract_data.get("contract_id", "custom"),
                display_name=contract_data.get("display_name", "自定义"),
                dialogue_density=tuple(contract_data.get("dialogue_density", (0.2, 0.45))),
                narration_ratio=tuple(contract_data.get("narration_ratio", (0.35, 0.8))),
                sentence_length_range=tuple(contract_data.get("sentence_length_range", (8, 45))),
                banned_phrases=tuple(contract_data.get("banned_phrases", ())),
                fatigue_words=tuple(contract_data.get("fatigue_words", ())),
                required_traits=tuple(contract_data.get("required_traits", ())),
                description=contract_data.get("description", ""),
                version=contract_data.get("version", 1),
                prompt_extra=contract_data.get("prompt_extra", ""),
            )
        except (TypeError, ValueError):
            return DEFAULT_STYLE_CONTRACT

    def check_compliance(self, text: str, contract: StyleContract) -> StyleGuardReport:
        """检查文本是否符合风格契约。"""
        guard = StyleGuard(contract)
        return guard.check(text)

    def save_contract(self, book_id: str, contract: StyleContract) -> None:
        """保存风格契约到 book.json。"""
        from dataclasses import asdict
        path = Path(self._books_dir) / book_id / "book.json"
        data = {}
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
        data["style_contract"] = asdict(contract)
        path.parent.mkdir(parents=True, exist_ok=True)
        # 使用原子写入模式
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
```

### 5. deps.py 更新

**文件**：`src/storyforge3/api/deps.py`

新增 4 个依赖注入函数：

```python
from storyforge3.services.audit_service import AuditService
from storyforge3.services.truth_service import TruthService
from storyforge3.services.prompt_service import PromptService
from storyforge3.services.style_service import StyleService

def get_audit_service(
    config: StoryForge3Config = Depends(get_config),
) -> AuditService:
    return AuditService(config=config)

def get_truth_service(
    config: StoryForge3Config = Depends(get_config),
) -> TruthService:
    return TruthService(config=config)

def get_prompt_service(
    registry: PromptRegistry = Depends(get_prompt_registry),
) -> PromptService:
    return PromptService(registry)

def get_style_service(
    config: StoryForge3Config = Depends(get_config),
) -> StyleService:
    return StyleService(config)
```

### 6. Protocol 返回类型修正

**文件**：`src/storyforge3/services/protocols.py`

修正 `AuditServiceProtocol.run_llm_audit` 返回类型：

```python
# 改前
async def run_llm_audit(self, text: str, context: str, *, model: str | None = None) -> AuditResult: ...

# 改后
async def run_llm_audit(self, text: str, context: str, *, model: str | None = None) -> LLMAuditResult: ...
```

需要在文件顶部增加 import：
```python
from storyforge3.audit.llm_auditor import LLMAuditResult
```

### 7. 测试

**文件**：`tests/test_service_alignment.py`（新建）

测试用例：

1. **`test_audit_service_run_mechanical`**：调用 `run_mechanical()` 返回 `AuditResult`
2. **`test_audit_service_run_llm_audit`**：mock LLM，调用 `run_llm_audit()` 返回 `LLMAuditResult`
3. **`test_truth_service_save_and_load`**：save → load_latest 返回相同数据
4. **`test_truth_service_load_history`**：save 3 章 → load_history 返回 3 条
5. **`test_truth_service_load_history_empty`**：无数据返回空列表
6. **`test_prompt_service_get_latest`**：get("compose") 返回模板
7. **`test_prompt_service_list_templates`**：返回包含 task_type 和 versions 的列表
8. **`test_style_service_default_contract`**：无 book.json 返回 DEFAULT_STYLE_CONTRACT
9. **`test_style_service_save_and_load_contract`**：save_contract → get_contract roundtrip
10. **`test_style_service_check_compliance`**：check_compliance 返回 StyleGuardReport
11. **`test_deps_inject_audit_service`**：验证 FastAPI 能注入 AuditService
12. **`test_deps_inject_truth_service`**：验证 FastAPI 能注入 TruthService

---

## 技术约束

1. **不改变现有 API 路由逻辑**：新 Service 不强制替代 ChapterService 内部调用
2. **不改变 ChapterWorkflow**：workflow.py 保持不变，Service 对齐是 API 层的事
3. **不引入新依赖**：所有 Service 封装现有模块
4. **不改变现有测试**：310 测试必须全部通过
5. **Protocol 返回类型修正仅限 AuditServiceProtocol**：只改 `run_llm_audit` 返回类型
6. **Service 构造函数接收可选依赖**：方便测试注入 mock
7. **中文注释**：公共方法有 docstring

---

## 验收

```powershell
cd storyforge3
.\.venv\Scripts\python.exe -m pytest tests/ -q   # 310 + 新增测试通过
ruff check .                                       # clean
```

功能验收：
1. `AuditService` 实现了 `AuditServiceProtocol` 的两个方法
2. `TruthService` 实现了 `TruthServiceProtocol` 的四个方法
3. `PromptService` 实现了 `PromptServiceProtocol` 的三个方法
4. `StyleService` 实现了 `StyleServiceProtocol` 的三个方法
5. 4 个新 Service 都通过 deps.py 注入
6. `AuditServiceProtocol.run_llm_audit` 返回类型修正为 `LLMAuditResult`
7. 全部 310 + 新增测试通过
8. ruff check clean

---

## 完成后回报格式

```
给 ClaudeCode 产品经理的执行结果：

Phase 5C-2（Service 架构对齐）：
- AuditService：[完成状态]
- TruthService：[完成状态]
- PromptService：[完成状态]
- StyleService：[完成状态]
- deps.py 注入：[完成状态]
- Protocol 返回类型修正：[完成状态]
- 新增测试数：N
- 全量测试：[310+N] passed
- ruff check：[clean/有警告]
- 改动文件列表：[...]
```

---

## 参考文件

1. `src/storyforge3/services/protocols.py` — 11 个 Protocol 定义
2. `src/storyforge3/audit/runner.py` — AuditRunner（待封装）
3. `src/storyforge3/audit/llm_auditor.py` — LLMAuditor（待封装）
4. `src/storyforge3/truth/extractor.py` — TruthExtractor（待封装）
5. `src/storyforge3/truth/store.py` — TruthStore（待封装）
6. `src/storyforge3/prompts/registry.py` — PromptRegistry（待封装）
7. `src/storyforge3/style/contract.py` — StyleContract + DEFAULT_STYLE_CONTRACT
8. `src/storyforge3/style/guard.py` — StyleGuard（待封装）
9. `src/storyforge3/api/deps.py` — 依赖注入
10. `src/storyforge3/config.py` — StoryForge3Config
