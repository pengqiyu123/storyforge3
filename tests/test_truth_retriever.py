from __future__ import annotations

from pathlib import Path

from storyforge3.truth.database import TruthDatabase, TruthEntry
from storyforge3.truth.retriever import TruthRetriever


def truth_entry(chapter_no: int, content: str, *, category: str = "plot_point", importance: float = 0.5) -> TruthEntry:
    return TruthEntry(
        id=None,
        book_id="lurenjia",
        chapter_no=chapter_no,
        category=category,
        content=content,
        importance=importance,
        related_chapters=(),
        created_at="2026-06-02T00:00:00+00:00",
    )


def test_retriever_formats_prompt_truth_with_priority_and_limit(tmp_path: Path) -> None:
    db = TruthDatabase(tmp_path / "truth.db")
    db.insert_entries("lurenjia", 10, [truth_entry(10, "当前章林默正在检测中心门口等待许青。", category="character_event", importance=0.4)])
    db.insert_entries("lurenjia", 9, [truth_entry(9, "许青发现林默的存在感残痕。", category="plot_point", importance=0.7)])
    db.insert_entries("lurenjia", 2, [truth_entry(2, "存在感系统过度使用会留下残痕。", category="world_rule", importance=0.95)])
    db.insert_entries("lurenjia", 1, [truth_entry(1, "无关的高分历史。", category="world_rule", importance=1.0)])
    retriever = TruthRetriever(db)

    text = retriever.retrieve_for_prompt(
        "lurenjia",
        10,
        "林默和许青讨论存在感残痕",
        max_entries=4,
        max_chars=1000,
    )

    assert text.splitlines() == [
        "[第10章][character_event][0.40] 当前章林默正在检测中心门口等待许青。",
        "[第9章][plot_point][0.70] 许青发现林默的存在感残痕。",
        "[第2章][world_rule][0.95] 存在感系统过度使用会留下残痕。",
    ]
    assert "无关的高分历史" not in text


def test_retriever_includes_high_importance_history_as_fallback(tmp_path: Path) -> None:
    db = TruthDatabase(tmp_path / "truth.db")
    db.insert_entries("lurenjia", 10, [truth_entry(10, "当前章林默正在检测中心门口。", category="character_event", importance=0.4)])
    db.insert_entries("lurenjia", 3, [truth_entry(3, "周砚知道残痕机制。", category="world_rule", importance=0.95)])
    retriever = TruthRetriever(db)

    text = retriever.retrieve_for_prompt(
        "lurenjia",
        10,
        "林默准备进入检测中心",
        max_entries=3,
        max_chars=1000,
    )

    assert "[第3章][world_rule][0.95] 周砚知道残痕机制。" in text


def test_retriever_respects_max_chars(tmp_path: Path) -> None:
    db = TruthDatabase(tmp_path / "truth.db")
    db.insert_entries(
        "lurenjia",
        8,
        [
            truth_entry(8, "林默需要记住许青的提醒。", importance=0.9),
            truth_entry(7, "这一条很长很长很长很长很长很长很长很长。", importance=0.9),
        ],
    )
    retriever = TruthRetriever(db)

    text = retriever.retrieve_for_prompt("lurenjia", 8, "林默许青", max_entries=5, max_chars=45)

    assert "林默需要记住许青的提醒。" in text
    assert "这一条很长" not in text
