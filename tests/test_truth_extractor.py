from __future__ import annotations

import asyncio

import pytest

from storyforge3.prompts.registry import create_default_registry
from storyforge3.truth.extractor import TruthExtractionError, TruthExtractor


def run(coro):
    return asyncio.run(coro)


class MockClient:
    def __init__(self, payload=None, error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error

    async def generate_json(self, task_name, system_prompt, user_payload, response_schema, **kwargs):
        if self.error:
            raise self.error
        return self.payload


def test_truth_extract_success(sample_chapter_text: str) -> None:
    payload = {
        "fact_assertions": ["林默进入副楼。"],
        "character_updates": [{"id": "lin_mo"}],
        "relationship_updates": [],
        "hook_updates": [],
        "irreversible_facts": [],
        "notes": [],
    }
    extractor = TruthExtractor(MockClient(payload), create_default_registry())
    truth = run(extractor.extract(8, sample_chapter_text))
    assert truth.chapter_no == 8
    assert truth.source == "runtime_native"
    assert truth.fact_assertions == ("林默进入副楼。",)


def test_truth_extract_normalizes_string_update_items(sample_chapter_text: str) -> None:
    payload = {
        "fact_assertions": ["林默进入副楼。"],
        "character_updates": ["林默开始怀疑检测中心。"],
        "relationship_updates": ["许青继续帮助林默。"],
        "hook_updates": ["副楼门后仍有异常声。"],
        "irreversible_facts": [],
        "notes": [],
    }
    extractor = TruthExtractor(MockClient(payload), create_default_registry())

    truth = run(extractor.extract(8, sample_chapter_text))

    assert truth.character_updates == ({"summary": "林默开始怀疑检测中心。"},)
    assert truth.relationship_updates == ({"summary": "许青继续帮助林默。"},)
    assert truth.hook_updates == ({"summary": "副楼门后仍有异常声。"},)


def test_truth_extract_failure_raises(sample_chapter_text: str) -> None:
    extractor = TruthExtractor(MockClient(error=RuntimeError("bad gateway")), create_default_registry())
    with pytest.raises(TruthExtractionError):
        run(extractor.extract(8, sample_chapter_text))


def test_empty_truth_is_rejected(sample_chapter_text: str) -> None:
    extractor = TruthExtractor(MockClient({"fact_assertions": []}), create_default_registry())
    with pytest.raises(TruthExtractionError):
        run(extractor.extract(8, sample_chapter_text))
