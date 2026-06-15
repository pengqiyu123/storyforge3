from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from storyforge3.models import TruthData
from storyforge3.storage import BookStorage, StoragePaths
from storyforge3.truth.store import TruthStore


@pytest.mark.asyncio
async def test_discard_preview_and_delete_endpoint(async_client, api_config):
    paths = StoragePaths(Path(api_config.books_dir))
    storage = BookStorage(paths.books_root)
    store = TruthStore(str(paths.books_root))
    _seed_discard_book(storage, store, paths, "book-a", target_chapter=4)

    preview = await async_client.get("/api/books/book-a/chapters/4/discard-preview")
    assert preview.status_code == 200
    body = preview.json()["data"]
    assert body["truth_db_rows"] == 7
    assert body["pipeline_lines_removed"] == 1
    assert body["state_removed"] is True
    assert "chapters/0004.md" in body["deleted_files"]
    assert body["backed_up_to"].replace("\\", "/").endswith("_trash/ch0004/001")

    assert (paths.book_dir("book-a") / "chapters" / "0004.md").exists()

    deleted = await async_client.delete("/api/books/book-a/chapters/4")
    assert deleted.status_code == 200
    data = deleted.json()["data"]
    assert data["truth_db_rows"] == 7
    assert data["pipeline_lines_removed"] == 1
    assert data["state_removed"] is True
    assert data["backed_up_to"].replace("\\", "/").endswith("_trash/ch0004/001")
    assert data["post_reconcile"]["max_chapter"] == 3
    assert data["post_reconcile"]["valid_chapter_count"] == 3
    assert not (paths.book_dir("book-a") / "chapters" / "0004.md").exists()

    second = await async_client.delete("/api/books/book-a/chapters/4")
    assert second.status_code == 200
    empty = second.json()["data"]
    assert empty["deleted_files"] == []
    assert empty["truth_db_rows"] == 0
    assert empty["pipeline_lines_removed"] == 0


def _seed_discard_book(storage: BookStorage, store: TruthStore, paths: StoragePaths, book_id: str, *, target_chapter: int) -> None:
    book_dir = paths.book_dir(book_id)
    book_dir.mkdir(parents=True, exist_ok=True)
    storage.write_json(
        paths.book_meta(book_id),
        {
            "book_id": book_id,
            "title": "测试书",
            "genre": "urban",
            "platform": "tomato",
            "status": "active",
            "target_chapters": 12,
            "chapter_word_count": 2500,
            "language": "zh",
            "current_chapter": target_chapter,
            "created_at": "2026-06-15T00:00:00+00:00",
            "updated_at": "2026-06-15T00:00:00+00:00",
        },
    )
    for chapter_no in (1, 2, 3):
        storage.write_text(paths.chapter_file(book_id, chapter_no), f"第{chapter_no}章正文")
    storage.write_text(paths.chapter_file(book_id, target_chapter), f"第{target_chapter}章正文")
    storage.write_json(paths.plan_file(book_id, target_chapter), {"chapter_no": target_chapter, "goal": "清空重产"})
    storage.write_json(
        paths.truth_file(book_id, target_chapter),
        {
            "chapter_no": target_chapter,
            "source": "runtime_native",
            "fact_assertions": ["第4章事实A", "第4章事实B"],
            "character_updates": [{"summary": "第4章角色变化"}],
            "relationship_updates": [{"summary": "第4章关系变化"}],
            "hook_updates": [{"summary": "第4章钩子"}],
            "irreversible_facts": ["第4章硬设定"],
            "notes": ["第4章备注"],
        },
    )
    storage.write_text(paths.export_file(book_id, target_chapter, "txt"), f"第{target_chapter}章导出")
    storage.write_text(book_dir / "exports" / f"chapter-{target_chapter:04d}.md", f"# 第{target_chapter}章")
    storage.write_text(book_dir / "exports" / f"chapter-{target_chapter:04d}-qidian.txt", f"第{target_chapter}章起点")
    storage.write_text(book_dir / "exports" / f"chapter-{target_chapter:04d}.txt.tmp", "partial")

    snapshot_zip = book_dir / "snapshots" / "20260615T000000000000Z_ch0004.zip"
    snapshot_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(snapshot_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("chapters/0004.md", "第4章正文")
    (book_dir / "snapshots" / "20260615T000000000000Z_ch0004.meta.json").write_text(
        json.dumps({"book_id": book_id, "chapter_no": target_chapter}, ensure_ascii=False),
        encoding="utf-8",
    )

    run_dir = paths.chapter_dir(book_id, target_chapter) / "runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "current_run.json").write_text(json.dumps({"run_id": "run-0004"}, ensure_ascii=False), encoding="utf-8")
    (run_dir / "run-0004.json").write_text(json.dumps({"run_id": "run-0004", "chapter_no": target_chapter}, ensure_ascii=False), encoding="utf-8")

    (book_dir / "runs").mkdir(parents=True, exist_ok=True)
    (book_dir / "runs" / "pipeline.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"book_id": book_id, "chapter_no": 3, "task": "draft"}, ensure_ascii=False),
                json.dumps({"book_id": book_id, "chapter_no": target_chapter, "task": "draft"}, ensure_ascii=False),
                "malformed-line",
                json.dumps({"book_id": "other-book", "chapter_no": target_chapter, "task": "draft"}, ensure_ascii=False),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    storage.write_json(
        paths.chapter_states(book_id),
        {
            f"{book_id}:0003": {"status": "drafted", "history": []},
            f"{book_id}:0004": {"status": "approved", "history": []},
        },
    )

    store.save(
        book_id,
        TruthData(
            chapter_no=target_chapter,
            source="runtime_native",
            fact_assertions=("第4章事实A", "第4章事实B"),
            character_updates=({"summary": "第4章角色变化"},),
            relationship_updates=({"summary": "第4章关系变化"},),
            hook_updates=({"summary": "第4章钩子"},),
            irreversible_facts=("第4章硬设定",),
            notes=("第4章备注",),
        ),
    )
    store.save(
        "book-b",
        TruthData(
            chapter_no=target_chapter,
            source="runtime_native",
            fact_assertions=("other row 1", "other row 2"),
            character_updates=(),
            relationship_updates=(),
            hook_updates=(),
            irreversible_facts=(),
            notes=(),
        ),
    )
