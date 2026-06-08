from __future__ import annotations

import math
import re
from typing import Any


class ChunkedGenerator:
    """Generate long chapter drafts through smaller provider calls."""

    def __init__(self, service: Any, *, chunk_target_chars: int = 500, max_chunks: int = 6) -> None:
        self.service = service
        self.chunk_target_chars = chunk_target_chars
        self.max_chunks = max_chunks

    async def generate(self, task_name: str, system_prompt: str, outline: str, context: dict) -> str:
        target_chars = _positive_int(context.get("target_chars"), self.chunk_target_chars)
        chunk_count = max(1, min(self.max_chunks, math.floor((target_chars + self.chunk_target_chars / 2) / self.chunk_target_chars)))
        plan = await self.service.generate_text(
            f"{task_name}_chunk_plan",
            system_prompt,
            {
                **_public_context(context),
                "outline": outline,
                "target_chars": target_chars,
                "chunk_count": chunk_count,
                "chunk_target_chars": self.chunk_target_chars,
                "task": "生成本章分段计划，约 200 字，只列出场景推进。",
            },
            model=context.get("model"),
            prompt_version=context.get("prompt_version"),
            max_output_tokens=800,
        )
        scenes = _extract_scenes(plan, fallback=outline, limit=chunk_count)
        chunks: list[str] = []
        for index, scene in enumerate(scenes, start=1):
            chunk = await self.service.generate_text(
                f"{task_name}_chunk",
                system_prompt,
                {
                    **_public_context(context),
                    "chunk_index": index,
                    "chunk_count": len(scenes),
                    "chunk_target_chars": self.chunk_target_chars,
                    "chapter_outline": outline,
                    "chunk_outline": scene,
                    "previous_chunk_tail": chunks[-1][-200:] if chunks else "",
                    "task": "只输出当前段落正文，保持与前文连贯。",
                },
                model=context.get("model"),
                prompt_version=context.get("prompt_version"),
                temperature=context.get("temperature"),
                max_output_tokens=context.get("chunk_max_output_tokens"),
            )
            if chunk.strip():
                chunks.append(chunk.strip())
        return "\n\n".join(chunks)


def _extract_scenes(plan: str, *, fallback: str, limit: int) -> list[str]:
    scenes: list[str] = []
    for line in plan.splitlines():
        text = re.sub(r"^\s*(?:[-*]|\d+[.、)]|第[一二三四五六七八九十]+[段幕场])\s*", "", line).strip()
        if text:
            scenes.append(text)
    if not scenes:
        scenes = [item.strip() for item in re.split(r"[；;]\s*", fallback) if item.strip()]
    if not scenes:
        scenes = [fallback.strip() or "推进本章剧情"]
    while len(scenes) < limit:
        scenes.append(scenes[-1])
    return scenes[:limit]


def _public_context(context: dict) -> dict:
    return {key: value for key, value in context.items() if key not in {"model", "prompt_version", "temperature", "chunk_max_output_tokens"}}


def _positive_int(value: object, fallback: int) -> int:
    return value if isinstance(value, int) and value > 0 else fallback
