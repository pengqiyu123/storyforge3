from __future__ import annotations

from storyforge3.cost.budget import ContextBudget
from storyforge3.cost.tracker import CostAccumulator, TokenEstimator, TokenUsage
from storyforge3.models import LLMCallRecord


def test_token_estimator_uses_chinese_1_5_chars_per_token() -> None:
    assert TokenEstimator().estimate("林默站在门口") == 4


def test_token_estimator_counts_other_chars_more_cheaply() -> None:
    assert TokenEstimator().estimate("abcd1234") == 2


def test_cost_accumulator_adds_llm_call_records() -> None:
    calls = (
        LLMCallRecord("draft", "gpt-5.5", "compose-v1", 150, 300, 1200.0, True),
        LLMCallRecord("truth", "gpt-5.5", "truth-v1", 50, 20, 400.0, True),
    )
    summary = CostAccumulator().from_llm_calls(calls).summary()
    assert summary.total_input_tokens == 200
    assert summary.total_output_tokens == 320
    assert summary.total_tokens == 520
    assert summary.call_count == 2


def test_cost_accumulator_accepts_estimated_usage() -> None:
    acc = CostAccumulator()
    acc.add_usage("draft", "test-model", TokenUsage(10, 20, estimated=True))
    summary = acc.summary()
    assert summary.total_tokens == 30
    assert summary.estimated is True


def test_context_budget_trims_low_priority_first() -> None:
    budget = ContextBudget(total_budget=100, output_reserve=10, max_utilization=1.0)
    allocation = budget.allocate(
        constraints=30,
        truth=30,
        direction=20,
        history=20,
        plan=20,
    )
    assert allocation.allocations["constraints"] == 30
    assert allocation.allocations["truth"] == 30
    assert allocation.allocations["direction"] == 20
    assert allocation.allocations["history"] == 10
    assert allocation.allocations["plan"] == 0
    assert allocation.trimmed_components == ("plan", "history")


def test_context_budget_keeps_priority_order_when_severely_constrained() -> None:
    budget = ContextBudget(total_budget=60, output_reserve=10, max_utilization=1.0)
    allocation = budget.allocate(
        constraints=30,
        truth=30,
        direction=20,
        history=20,
        plan=20,
    )
    assert allocation.allocations == {
        "constraints": 30,
        "truth": 20,
        "direction": 0,
        "history": 0,
        "plan": 0,
    }
