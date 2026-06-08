from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from storyforge3.context.context_block import ContextBlock, ContextPriority


@dataclass
class ContextPackage:
    """Assembled context for a single LLM call."""

    task: str
    blocks: list[ContextBlock] = field(default_factory=list)
    budget_chars: int | None = None

    @property
    def total_chars(self) -> int:
        return sum(block.char_count for block in self.blocks)

    @property
    def total_tokens(self) -> int:
        return sum(block.estimate_tokens() for block in self.blocks)

    def add(self, block: ContextBlock) -> None:
        self.blocks.append(block)

    def trim_to_budget(self) -> int:
        """Trim LOW, then MEDIUM, then HIGH blocks until within budget."""
        if self.budget_chars is None or self.total_chars <= self.budget_chars:
            return 0
        trimmed = 0
        for priority in (ContextPriority.LOW, ContextPriority.MEDIUM, ContextPriority.HIGH):
            for index in range(len(self.blocks) - 1, -1, -1):
                if self.total_chars <= self.budget_chars:
                    return trimmed
                if self.blocks[index].priority == priority:
                    self.blocks.pop(index)
                    trimmed += 1
        return trimmed

    def to_prompt_text(self) -> str:
        """Serialize all blocks into a prompt string with source headers."""
        return "\n\n".join(f"[{block.source}]\n{block.content}" for block in self.blocks)

    def sources_summary(self) -> list[dict[str, Any]]:
        """Return source metadata for diagnostics and logging."""
        return [
            {
                "source": block.source,
                "priority": block.priority.name,
                "chars": block.char_count,
                "tokens": block.estimate_tokens(),
            }
            for block in self.blocks
        ]
