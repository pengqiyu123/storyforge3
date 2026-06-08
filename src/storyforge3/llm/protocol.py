from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ResponsesAPIRequest:
    """Request sent to CCSwitch /responses."""

    model: str
    system_prompt: str
    user_payload: str
    response_schema: dict | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None


@dataclass(frozen=True)
class ResponsesAPIResponse:
    """Response returned by CCSwitch /responses."""

    output_text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    model: str | None = None
    raw: dict = field(default_factory=dict)
