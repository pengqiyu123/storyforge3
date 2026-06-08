from __future__ import annotations

import json
import re


class JSONTextParseError(ValueError):
    pass


def parse_json_text(text: str) -> dict:
    """Parse either bare JSON or a ```json fenced block."""
    candidates = [_extract_fenced_json(text), text]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            data = json.loads(candidate.strip())
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    raise JSONTextParseError("LLM response does not contain a JSON object")


def _extract_fenced_json(text: str) -> str:
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1) if match else ""
