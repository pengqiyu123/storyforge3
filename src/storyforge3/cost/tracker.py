from __future__ import annotations

from dataclasses import dataclass

from storyforge3.models import LLMCallRecord


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    estimated: bool = False

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class CostRecord:
    task_name: str
    model: str
    usage: TokenUsage


@dataclass(frozen=True)
class CostSummary:
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    call_count: int
    estimated: bool


class TokenEstimator:
    """Small deterministic estimator: Chinese 1.5 chars/token, other 4 chars/token."""

    def estimate(self, text: str) -> int:
        if not text:
            return 0
        chinese_chars = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
        other_chars = len(text) - chinese_chars
        return max(1, int(chinese_chars / 1.5 + other_chars / 4.0))

    def estimate_payload(self, payload: dict) -> int:
        return self.estimate(str(payload))


class CostAccumulator:
    def __init__(self) -> None:
        self.records: list[CostRecord] = []

    def add_usage(self, task_name: str, model: str, usage: TokenUsage) -> None:
        self.records.append(CostRecord(task_name, model, usage))

    def from_llm_calls(self, calls: tuple[LLMCallRecord, ...]) -> CostAccumulator:
        for call in calls:
            self.add_usage(
                call.task_name,
                call.model,
                TokenUsage(call.input_tokens or 0, call.output_tokens or 0, estimated=False),
            )
        return self

    def summary(self) -> CostSummary:
        input_tokens = sum(record.usage.input_tokens for record in self.records)
        output_tokens = sum(record.usage.output_tokens for record in self.records)
        return CostSummary(
            total_input_tokens=input_tokens,
            total_output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            call_count=len(self.records),
            estimated=any(record.usage.estimated for record in self.records),
        )
