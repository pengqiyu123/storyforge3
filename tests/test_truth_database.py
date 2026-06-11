from __future__ import annotations

from pathlib import Path

from storyforge3.models import TruthData
from storyforge3.truth.database import TruthDatabase, TruthEntry
from storyforge3.truth.store import TruthStore


def entry(
    content: str,
    *,
    category: str = "plot_point",
    importance: float = 0.5,
    related_chapters: tuple[int, ...] = (),
) -> TruthEntry:
    return TruthEntry(
        id=None,
        book_id="lurenjia",
        chapter_no=1,
        category=category,
        content=content,
        importance=importance,
        related_chapters=related_chapters,
        created_at="2026-06-02T00:00:00+00:00",
    )


def test_truth_database_crud_and_chapter_queries(tmp_path: Path) -> None:
    db = TruthDatabase(tmp_path / "truth.db")
    db.insert_entries(
        "lurenjia",
        3,
        [
            entry("林默在检测中心登记异常。", category="character_event", importance=0.8, related_chapters=(1, 2)),
            entry("存在感系统会留下残痕。", category="world_rule", importance=0.6),
        ],
    )

    rows = db.query_by_chapter("lurenjia", 3)

    assert [row.content for row in rows] == ["林默在检测中心登记异常。", "存在感系统会留下残痕。"]
    assert rows[0].book_id == "lurenjia"
    assert rows[0].chapter_no == 3
    assert rows[0].id is not None
    assert rows[0].related_chapters == (1, 2)

    db.delete_chapter("lurenjia", 3)
    assert db.query_by_chapter("lurenjia", 3) == []


def test_truth_database_relevant_query_uses_keywords_importance_recency_and_category(tmp_path: Path) -> None:
    db = TruthDatabase(tmp_path / "truth.db")
    db.insert_entries(
        "lurenjia",
        1,
        [entry("检测中心大厅有三道门。", category="world_rule", importance=0.95)],
    )
    db.insert_entries(
        "lurenjia",
        8,
        [entry("林默答应许青进入检测中心复查。", category="character_event", importance=0.6)],
    )
    db.insert_entries(
        "lurenjia",
        9,
        [entry("许青发现林默的存在感残痕。", category="plot_point", importance=0.55)],
    )
    db.insert_entries(
        "lurenjia",
        9,
        [entry("无关高分设定。", category="world_rule", importance=0.99)],
    )

    rows = db.query_relevant("lurenjia", "林默和许青准备进入检测中心", limit=3, min_importance=0.3)

    assert [row.content for row in rows] == [
        "林默答应许青进入检测中心复查。",
        "许青发现林默的存在感残痕。",
        "检测中心大厅有三道门。",
    ]


def test_truth_database_recent_query_returns_last_n_chapters(tmp_path: Path) -> None:
    db = TruthDatabase(tmp_path / "truth.db")
    for chapter_no in range(1, 8):
        db.insert_entries("lurenjia", chapter_no, [entry(f"第{chapter_no}章事实。", importance=0.5)])

    rows = db.query_recent("lurenjia", last_n_chapters=3)

    assert [row.chapter_no for row in rows] == [5, 6, 7]
    assert [row.content for row in rows] == ["第5章事实。", "第6章事实。", "第7章事实。"]


def test_truth_store_dual_writes_json_and_sqlite(tmp_path: Path) -> None:
    store = TruthStore(str(tmp_path / "books"))
    truth = TruthData(
        chapter_no=4,
        source="runtime_native",
        fact_assertions=("林默进入检测中心。", "存在感系统留下残痕。"),
        character_updates=({"summary": "许青开始信任林默。"},),
        relationship_updates=({"summary": "林默和许青形成合作。"},),
        hook_updates=({"summary": "检测中心暗门未解决。"},),
        irreversible_facts=("周砚知道残痕机制。",),
        notes=("需要保持林默谨慎。",),
    )

    json_path = store.save("lurenjia", truth)
    db_rows = store.database.query_by_chapter("lurenjia", 4)

    assert json_path.exists()
    assert len(db_rows) == 7
    assert "林默进入检测中心。" in [row.content for row in db_rows]
    assert {row.category for row in db_rows} == {"plot_point", "character_event", "relationship", "world_rule"}


def test_truth_store_load_history_returns_sorted_truth_data(tmp_path: Path) -> None:
    store = TruthStore(str(tmp_path / "books"))
    store.save(
        "lurenjia",
        TruthData(
            chapter_no=3,
            source="runtime_native",
            fact_assertions=("第3章事实。",),
            character_updates=(),
            relationship_updates=(),
            hook_updates=(),
            irreversible_facts=(),
            notes=(),
        ),
    )
    store.save(
        "lurenjia",
        TruthData(
            chapter_no=1,
            source="runtime_native",
            fact_assertions=("第1章事实。",),
            character_updates=(),
            relationship_updates=(),
            hook_updates=(),
            irreversible_facts=(),
            notes=(),
        ),
    )

    history = store.load_history("lurenjia")

    assert [item.chapter_no for item in history] == [1, 3]


def test_truth_store_load_history_returns_empty_for_missing_book(tmp_path: Path) -> None:
    store = TruthStore(str(tmp_path / "books"))

    assert store.load_history("missing") == []
