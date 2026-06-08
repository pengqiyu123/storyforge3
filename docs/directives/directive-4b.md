# Codex 指令：Phase 4B — Context Source Tracking

> 发出日期：2026-06-08
> 产品经理：Claude Code PM
> 执行者：Codex
> 前置条件：Phase 4A 已通过

---

## 任务概述

引入 `ContextBlock` 和 `ContextPackage` 数据结构，将上下文拼装从硬编码字典改为可追踪、可裁剪的结构化对象。首个迁移点是 draft 步骤。

---

## 背景

当前 `workflow.py` 的 `step_draft()` 方法中，payload 手动拼装了 `book_context`、`world`、`characters`、`relevant_truth`、`previous_chapter_tail` 等字段。这些字段没有：
1. 来源追踪（不知道哪块上下文来自哪里）
2. 预算管理（不知道各块占多少 token，无法按优先级裁剪）
3. 可审计性（无法事后查看送入 LLM 的上下文构成）

---

## 修改目标

### 1. 新增 `src/storyforge3/context/` 模块

```
src/storyforge3/context/
├── __init__.py          # 导出 ContextBlock, ContextPackage, ContextPriority
├── context_block.py     # ContextBlock dataclass
└── context_package.py   # ContextPackage dataclass + 裁剪逻辑
```

### 2. `ContextBlock` 定义

```python
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class ContextPriority(IntEnum):
    """Budget trim order: LOW trimmed first."""
    CRITICAL = 0  # 必须：当前章目标、前章尾部
    HIGH = 1      # 重要：世界规则、角色档案、truth 检索
    MEDIUM = 2    # 补充：context.md 全文
    LOW = 3       # 可选：风格样本、额外参考


@dataclass(frozen=True)
class ContextBlock:
    """One named slice of LLM prompt context."""
    source: str                        # "chapter_goal" | "world_rules" | "character_profile" | "truth_retrieval" | ...
    priority: ContextPriority
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def char_count(self) -> int:
        return len(self.content)

    def estimate_tokens(self) -> int:
        """Rough CJK token estimate: ~1.5 chars/token."""
        return max(1, len(self.content) * 2 // 3)
```

### 3. `ContextPackage` 定义

```python
from __future__ import annotations

import json
from dataclasses import dataclass, field

from storyforge3.context.context_block import ContextBlock, ContextPriority


@dataclass
class ContextPackage:
    """Assembled context for a single LLM call."""
    task: str                          # "draft" | "revise" | "truth_extract" | "audit"
    blocks: list[ContextBlock] = field(default_factory=list)
    budget_chars: int | None = None    # max chars allowed; None = unlimited

    @property
    def total_chars(self) -> int:
        return sum(block.char_count for block in self.blocks)

    @property
    def total_tokens(self) -> int:
        return sum(block.estimate_tokens() for block in self.blocks)

    def add(self, block: ContextBlock) -> None:
        self.blocks.append(block)

    def trim_to_budget(self) -> int:
        """Trim LOW → MEDIUM → HIGH blocks until within budget. Returns trimmed count."""
        if self.budget_chars is None or self.total_chars <= self.budget_chars:
            return 0
        trimmed = 0
        for priority_level in (ContextPriority.LOW, ContextPriority.MEDIUM, ContextPriority.HIGH):
            for i in range(len(self.blocks) - 1, -1, -1):
                if self.total_chars <= self.budget_chars:
                    return trimmed
                if self.blocks[i].priority == priority_level:
                    self.blocks.pop(i)
                    trimmed += 1
        return trimmed

    def to_prompt_text(self) -> str:
        """Serialize all blocks into a single prompt string with source headers."""
        parts: list[str] = []
        for block in self.blocks:
            header = f"[{block.source}]"
            parts.append(f"{header}\n{block.content}")
        return "\n\n".join(parts)

    def sources_summary(self) -> list[dict[str, Any]]:
        """Return a summary of sources and their sizes for logging."""
        return [
            {"source": b.source, "priority": b.priority.name, "chars": b.char_count, "tokens": b.estimate_tokens()}
            for b in self.blocks
        ]
```

### 4. 迁移 `step_draft()` 的上下文拼装

在 `workflow.py` 的 `step_draft()` 中，将 payload 构建改为使用 `ContextPackage`：

```python
async def step_draft(self, plan: str, ctx: BookContext, chapter_no: int) -> str:
    template = self.registry.get_latest("compose")
    prompt = self.registry.render_system_prompt(template, chapter_no=chapter_no)
    style_prompt = self._style_prompt_fragment(ctx.book_id)
    if style_prompt:
        prompt = f"{prompt}\n\n{style_prompt}"

    # --- 新增：用 ContextPackage 组装上下文 ---
    package = ContextPackage(task="draft", budget_chars=12000)
    package.add(ContextBlock("chapter_goal", ContextPriority.CRITICAL, plan))
    previous_tail = ctx.previous_chapters[-1][-1800:] if ctx.previous_chapters else ""
    if previous_tail:
        package.add(ContextBlock("previous_chapter_tail", ContextPriority.CRITICAL, previous_tail))
    if ctx.context_text:
        package.add(ContextBlock("book_context", ContextPriority.MEDIUM, ctx.context_text))
    if ctx.world:
        world_text = "\n".join(f"{k}: {v}" for k, v in ctx.world.items() if v)
        package.add(ContextBlock("world_rules", ContextPriority.HIGH, world_text))
    if ctx.characters:
        chars_text = "\n".join(
            f"{c['name']}({c['role']}): {c['profile']}" for c in ctx.characters if c.get("name")
        )
        package.add(ContextBlock("character_profiles", ContextPriority.HIGH, chars_text))
    truth_text = self.truth_retriever.retrieve_for_prompt(
        ctx.book_id, chapter_no, "\n".join((plan, ctx.context_text, previous_tail)), max_chars=4000,
    )
    if truth_text:
        package.add(ContextBlock("truth_retrieval", ContextPriority.HIGH, truth_text))

    trimmed = package.trim_to_budget()
    if trimmed:
        logger.warning(f"draft context trimmed {trimmed} blocks")
    # --- ContextPackage 组装结束 ---

    prompt_version = f"{template.prompt_id}:v{template.version}"
    payload = {
        "book_id": ctx.book_id,
        "chapter_no": chapter_no,
        "book_context": ctx.context_text,
        "previous_chapter_tail": previous_tail,
        "world": ctx.world,
        "characters": ctx.characters,
        "relevant_truth": truth_text,
        "plan": plan,
        "task": "根据计划直接输出下一章正文。",
    }
    # ... 后续逻辑不变（chunked 或直接 generate_text）
```

**注意**：这一步是渐进式迁移。payload 字典暂时保留（保持 LLM 输入兼容），`ContextPackage` 作为内部追踪层先到位。后续 Phase 可以逐步替换 payload 为 `package.to_prompt_text()`。

### 5. `step_revise()` 的 truth 检索也迁移

`step_revise()` 中有两处 `self.truth_retriever.retrieve_for_prompt()` 调用，各自构建 truth block。由于 revise 的上下文更短（patch revise 的 truth 只取 1200 chars），可以为 revise 也创建 `ContextPackage`，但这步是可选的。**最低要求**：只迁移 draft 步骤。

---

## 测试要求

新增 `tests/test_context_package.py`：

1. **test_context_block_char_count**：验证 `char_count` 正确
2. **test_context_block_estimate_tokens**：验证 `estimate_tokens()` 合理（中文文本约 1.5 char/token）
3. **test_package_add_and_total**：添加多个 block，验证 `total_chars` 和 `total_tokens`
4. **test_trim_removes_low_first**：3 个 block（HIGH/MEDIUM/LOW），budget 只能容纳 2 个，验证 LOW 被移除
5. **test_trim_removes_medium_second**：3 个 block（HIGH/MEDIUM/LOW），budget 只能容纳 1 个，验证 LOW + MEDIUM 被移除
6. **test_trim_does_not_remove_critical**：budget 极小，验证 CRITICAL 不被移除
7. **test_to_prompt_text_format**：验证输出格式 `[source]\ncontent`，block 之间用 `\n\n` 分隔
8. **test_sources_summary**：验证 summary 列表结构正确
9. **test_trim_with_unlimited_budget**：`budget_chars=None` 时 trim 不移除任何 block

---

## 验收

```powershell
ruff check src/storyforge3/context/ src/storyforge3/workflow.py
.\.venv\Scripts\python.exe -m pytest tests/test_context_package.py -v
.\.venv\Scripts\python.exe -m pytest -q   # 全量测试不退步
```

---

## 完成后回报格式

```
给 ClaudeCode 产品经理的执行结果：

Phase 4B（Context Source Tracking）：
- ContextBlock / ContextPackage 定义：[完成状态]
- draft 步骤迁移：[完成状态]
- 新增测试数：N
- 全量测试：N passed
- ruff check：[clean / 有 warnings]
```
