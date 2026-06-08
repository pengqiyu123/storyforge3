from __future__ import annotations

import asyncio

from storyforge3.config import StoryForge3Config
from storyforge3.services.chapter_service import ChapterService
from storyforge3.services.length_normalizer import LengthNormalizer, LengthNormalizationResult


def run(coro):
    return asyncio.run(coro)


class MockTextLLM:
    def __init__(self, text: str = "调整后的正文") -> None:
        self.text = text
        self.calls: list[dict] = []

    async def generate_text(self, task_name, system_prompt, user_payload, **kwargs):
        self.calls.append(
            {
                "task_name": task_name,
                "system_prompt": system_prompt,
                "payload": user_payload,
                "model": kwargs.get("model"),
                "prompt_version": kwargs.get("prompt_version"),
            }
        )
        return self.text


def chinese_text(chars: int) -> str:
    return "林" * chars


def test_length_normalizer_returns_original_inside_soft_range() -> None:
    llm = MockTextLLM()
    result = run(LengthNormalizer(llm, StoryForge3Config()).normalize(chinese_text(1000), target_chars=1000))
    assert result == LengthNormalizationResult(text=chinese_text(1000), action="none", original_chars=1000, final_chars=1000)
    assert llm.calls == []


def test_length_normalizer_does_not_call_llm_outside_soft_but_inside_hard() -> None:
    llm = MockTextLLM()
    result = run(LengthNormalizer(llm, StoryForge3Config()).normalize(chinese_text(1200), target_chars=1000))
    assert result.action == "none"
    assert llm.calls == []


def test_length_normalizer_compresses_above_hard_range() -> None:
    llm = MockTextLLM(chinese_text(1100))
    result = run(LengthNormalizer(llm, StoryForge3Config(writer_model="writer-model")).normalize(chinese_text(1800), target_chars=1000, hard_range=(700, 1400)))
    assert result.action == "compress"
    assert result.final_chars == 1100
    assert llm.calls[0]["task_name"] == "length_normalize"
    assert llm.calls[0]["payload"]["action"] == "compress"
    assert llm.calls[0]["model"] == "writer-model"


def test_length_normalizer_expands_below_hard_range() -> None:
    llm = MockTextLLM(chinese_text(900))
    result = run(LengthNormalizer(llm, StoryForge3Config()).normalize(chinese_text(500), target_chars=1000, hard_range=(700, 1400)))
    assert result.action == "expand"
    assert result.original_chars == 500
    assert result.final_chars == 900


def test_chapter_service_normalize_length_uses_normalizer(config: StoryForge3Config) -> None:
    llm = MockTextLLM(chinese_text(900))
    result = run(ChapterService(config, llm=llm).normalize_length(chinese_text(500), target_chars=1000, hard_range=(700, 1400)))
    assert result.action == "expand"
    assert result.text == chinese_text(900)
