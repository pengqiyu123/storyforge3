from __future__ import annotations

import json

from storyforge3.cost.tracker import TokenEstimator


def estimate_tokens(text: str) -> int:
    return TokenEstimator().estimate(text)


def describe_prompt(label: str, prompt: str, payload: dict, *, emit=print) -> None:
    payload_text = json.dumps(payload, ensure_ascii=False)
    total_text = f"{prompt}\n\n{payload_text}"
    emit(
        f"[DIAG] {label}: prompt={len(prompt)} chars/{estimate_tokens(prompt)} tokens, "
        f"payload={len(payload_text)} chars/{estimate_tokens(payload_text)} tokens, "
        f"total={len(total_text)} chars/{estimate_tokens(total_text)} tokens"
    )
    emit(f"[DIAG] {label} payload_keys={list(payload.keys())}")
    emit(f"[DIAG] {label} prompt first 500 chars: {prompt[:500]}")

