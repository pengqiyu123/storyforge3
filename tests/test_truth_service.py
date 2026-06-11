from __future__ import annotations

import asyncio

from storyforge3.config import StoryForge3Config
from storyforge3.models import TruthData
from storyforge3.services.truth_service import TruthService


def run(coro):
    return asyncio.run(coro)


def truth(chapter_no: int, fact: str | None = None) -> TruthData:
    return TruthData(
        chapter_no=chapter_no,
        source="test",
        fact_assertions=(fact or f"第{chapter_no}章事实。",),
        character_updates=({"summary": f"第{chapter_no}章角色变化。"},),
        relationship_updates=(),
        hook_updates=({"summary": f"第{chapter_no}章钩子变化。"},),
        irreversible_facts=(f"第{chapter_no}章不可逆事实。",),
        notes=(),
    )


class MockExtractor:
    def __init__(self, result: TruthData) -> None:
        self.result = result
        self.calls: list[tuple[int, str, TruthData | None]] = []

    async def extract(self, chapter_no: int, text: str, prev: TruthData | None = None) -> TruthData:
        self.calls.append((chapter_no, text, prev))
        return self.result


def test_extract_uses_injected_async_extractor(config: StoryForge3Config) -> None:
    previous = truth(7)
    result = truth(8, "林默进入副楼。")
    extractor = MockExtractor(result)
    service = TruthService(config=config, extractor=extractor)

    extracted = run(service.extract(8, "章节正文", previous))

    assert extracted == result
    assert extractor.calls == [(8, "章节正文", previous)]


def test_save_persists_truth_json(config: StoryForge3Config) -> None:
    service = TruthService(config=config)
    item = truth(3, "检测中心留下残痕。")

    service.save("lurenjia", item)

    loaded = service.load_latest("lurenjia")
    assert loaded == item


def test_load_latest_returns_highest_chapter(config: StoryForge3Config) -> None:
    service = TruthService(config=config)
    service.save("lurenjia", truth(1, "第1章事实。"))
    service.save("lurenjia", truth(4, "第4章事实。"))
    service.save("lurenjia", truth(2, "第2章事实。"))

    latest = service.load_latest("lurenjia")

    assert latest is not None
    assert latest.chapter_no == 4
    assert latest.fact_assertions == ("第4章事实。",)


def test_load_history_returns_chapter_order(config: StoryForge3Config) -> None:
    service = TruthService(config=config)
    service.save("lurenjia", truth(5, "第5章事实。"))
    service.save("lurenjia", truth(2, "第2章事实。"))

    history = service.load_history("lurenjia")

    assert [item.chapter_no for item in history] == [2, 5]
    assert [item.fact_assertions[0] for item in history] == ["第2章事实。", "第5章事实。"]


def test_load_latest_returns_none_for_empty_history(config: StoryForge3Config) -> None:
    service = TruthService(config=config)

    latest = service.load_latest("lurenjia")

    assert latest is None


def test_load_history_returns_empty_for_missing_book(config: StoryForge3Config) -> None:
    service = TruthService(config=config)

    history = service.load_history("missing-book")

    assert history == []
