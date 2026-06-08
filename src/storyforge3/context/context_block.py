from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class ContextPriority(IntEnum):
    """Budget trim order: LOW is trimmed first."""

    CRITICAL = 0
    HIGH = 1
    MEDIUM = 2
    LOW = 3


@dataclass(frozen=True)
class ContextBlock:
    """One named slice of LLM prompt context."""

    source: str
    priority: ContextPriority
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def char_count(self) -> int:
        return len(self.content)

    def estimate_tokens(self) -> int:
        """Rough CJK token estimate: about 1.5 chars per token."""
        return max(1, len(self.content) * 2 // 3)
