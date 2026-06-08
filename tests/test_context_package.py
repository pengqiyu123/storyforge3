from __future__ import annotations

from storyforge3.context import ContextBlock, ContextPackage, ContextPriority


def test_context_block_char_count() -> None:
    block = ContextBlock("book_context", ContextPriority.MEDIUM, "林默站在门口。")

    assert block.char_count == 7


def test_context_block_estimate_tokens() -> None:
    block = ContextBlock("truth_retrieval", ContextPriority.HIGH, "林默发现异常")

    assert block.estimate_tokens() == 4


def test_package_add_and_total() -> None:
    package = ContextPackage(task="draft")

    package.add(ContextBlock("chapter_goal", ContextPriority.CRITICAL, "目标"))
    package.add(ContextBlock("world_rules", ContextPriority.HIGH, "世界规则"))

    assert package.total_chars == 6
    assert package.total_tokens == 3


def test_trim_removes_low_first() -> None:
    package = ContextPackage(
        task="draft",
        budget_chars=8,
        blocks=[
            ContextBlock("high", ContextPriority.HIGH, "H" * 4),
            ContextBlock("medium", ContextPriority.MEDIUM, "M" * 4),
            ContextBlock("low", ContextPriority.LOW, "L" * 4),
        ],
    )

    assert package.trim_to_budget() == 1
    assert [block.source for block in package.blocks] == ["high", "medium"]


def test_trim_removes_medium_second() -> None:
    package = ContextPackage(
        task="draft",
        budget_chars=4,
        blocks=[
            ContextBlock("high", ContextPriority.HIGH, "H" * 4),
            ContextBlock("medium", ContextPriority.MEDIUM, "M" * 4),
            ContextBlock("low", ContextPriority.LOW, "L" * 4),
        ],
    )

    assert package.trim_to_budget() == 2
    assert [block.source for block in package.blocks] == ["high"]


def test_trim_does_not_remove_critical() -> None:
    package = ContextPackage(
        task="draft",
        budget_chars=1,
        blocks=[ContextBlock("chapter_goal", ContextPriority.CRITICAL, "C" * 10)],
    )

    assert package.trim_to_budget() == 0
    assert [block.source for block in package.blocks] == ["chapter_goal"]
    assert package.total_chars == 10


def test_to_prompt_text_format() -> None:
    package = ContextPackage(
        task="draft",
        blocks=[
            ContextBlock("chapter_goal", ContextPriority.CRITICAL, "目标"),
            ContextBlock("world_rules", ContextPriority.HIGH, "规则"),
        ],
    )

    assert package.to_prompt_text() == "[chapter_goal]\n目标\n\n[world_rules]\n规则"


def test_sources_summary() -> None:
    package = ContextPackage(
        task="draft",
        blocks=[ContextBlock("chapter_goal", ContextPriority.CRITICAL, "目标", {"chapter_no": 8})],
    )

    assert package.sources_summary() == [
        {"source": "chapter_goal", "priority": "CRITICAL", "chars": 2, "tokens": 1}
    ]


def test_trim_with_unlimited_budget() -> None:
    package = ContextPackage(
        task="draft",
        budget_chars=None,
        blocks=[
            ContextBlock("medium", ContextPriority.MEDIUM, "M" * 100),
            ContextBlock("low", ContextPriority.LOW, "L" * 100),
        ],
    )

    assert package.trim_to_budget() == 0
    assert [block.source for block in package.blocks] == ["medium", "low"]
