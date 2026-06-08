from __future__ import annotations

from dataclasses import dataclass


PRIORITY_ORDER = ("constraints", "truth", "direction", "history", "plan")
TRIM_ORDER = tuple(reversed(PRIORITY_ORDER))


@dataclass(frozen=True)
class ContextAllocation:
    allocations: dict[str, int]
    total_allocated: int
    budget_remaining: int
    trimmed_components: tuple[str, ...]


@dataclass(frozen=True)
class ContextBudget:
    total_budget: int
    output_reserve: int = 4000
    max_utilization: float = 0.85

    @property
    def available_for_input(self) -> int:
        return max(0, int(self.total_budget * self.max_utilization) - self.output_reserve)

    def allocate(
        self,
        *,
        constraints: int = 0,
        truth: int = 0,
        direction: int = 0,
        history: int = 0,
        plan: int = 0,
    ) -> ContextAllocation:
        allocations = {
            "constraints": max(0, constraints),
            "truth": max(0, truth),
            "direction": max(0, direction),
            "history": max(0, history),
            "plan": max(0, plan),
        }
        trimmed: list[str] = []
        for component in TRIM_ORDER:
            excess = sum(allocations.values()) - self.available_for_input
            if excess <= 0:
                break
            if allocations[component] <= 0:
                continue
            reduction = min(allocations[component], excess)
            allocations[component] -= reduction
            trimmed.append(component)
        total = sum(allocations.values())
        return ContextAllocation(
            allocations=allocations,
            total_allocated=total,
            budget_remaining=max(0, self.available_for_input - total),
            trimmed_components=tuple(trimmed),
        )
