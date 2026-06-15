from __future__ import annotations

import json
import zipfile
from hashlib import sha256
from pathlib import Path

from storyforge3.models import TruthData
from storyforge3.services.chapter_discarder import ChapterDiscarder
from storyforge3.storage import BookStorage, StoragePaths
from storyforge3.truth.store import TruthStore


def test_chapter_discarder_preview_lists_artifacts_and_is_read_only(tmp_path: Path) -> None:
    paths = StoragePaths(tmp_path / "books")
    storage = BookStorage(paths.books_root)
    store = TruthStore(str(paths.books_root))
    _seed_discard_book(storage, store, paths, "book-a", target_chapter=4)

    discarder = ChapterDiscarder(storage, paths)
    before_hash = _fingerprint(paths.book_dir("book-a") / "chapters" / "0004.md")

    preview = discarder.preview("book-a", 4)

    assert preview.book_id == "book-a"
    assert preview.chapter_no == 4
    assert preview.truth_db_rows == 7
    assert preview.pipeline_lines_removed == 1
    assert preview.state_removed is True
    assert sorted(preview.deleted_files) == sorted(
        [
            "chapters/0004.md",
            "plans/0004.json",
            "truth/chapter-0004.json",
            "exports/chapter-0004.md",
            "exports/chapter-0004-qidian.txt",
            "exports/chapter-0004.txt",
            "snapshots/20260615T000000000000Z_ch0004.meta.json",
            "snapshots/20260615T000000000000Z_ch0004.zip",
            "chapters/0004/runs/current_run.json",
            "chapters/0004/runs/run-0004.json",
        ]
    )
    assert preview.backed_up_to.replace("\\", "/").endswith("_trash/ch0004/001")
    assert _fingerprint(paths.book_dir("book-a") / "chapters" / "0004.md") == before_hash


def test_chapter_discarder_discard_backs_up_and_cleans_target_scope(tmp_path: Path) -> None:
    paths = StoragePaths(tmp_path / "books")
    storage = BookStorage(paths.books_root)
    store = TruthStore(str(paths.books_root))
    _seed_discard_book(storage, store, paths, "book-a", target_chapter=4)

    discarder = ChapterDiscarder(storage, paths)
    result = discarder.discard("book-a", 4)

    assert result.book_id == "book-a"
    assert result.chapter_no == 4
    assert result.truth_db_rows == 7
    assert result.pipeline_lines_removed == 1
    assert result.state_removed is True
    assert result.backed_up_to is not None
    assert result.backed_up_to.replace("\\", "/").endswith("_trash/ch0004/001")
    assert result.post_reconcile.max_chapter == 3
    assert result.post_reconcile.valid_chapter_count == 3
    assert result.post_reconcile.highest_contiguous_chapter == 3
    assert result.post_reconcile.next_writable_chapter_no == 4
    assert result.post_reconcile.has_blocking_inconsistency is False
    assert sorted(result.deleted_files) == sorted(
        [
            "chapters/0004.md",
            "plans/0004.json",
            "truth/chapter-0004.json",
            "exports/chapter-0004.md",
            "exports/chapter-0004-qidian.txt",
            "exports/chapter-0004.txt",
            "snapshots/20260615T000000000000Z_ch0004.meta.json",
            "snapshots/20260615T000000000000Z_ch0004.zip",
            "chapters/0004/runs/current_run.json",
            "chapters/0004/runs/run-0004.json",
        ]
    )
    assert sorted(result.rewritten_files) == ["runs/pipeline.jsonl", "state/chapter_states.json"]

    book_dir = paths.book_dir("book-a")
    backup_dir = Path(result.backed_up_to)
    assert not (book_dir / "chapters" / "0004.md").exists()
    assert not (book_dir / "plans" / "0004.json").exists()
    assert not (book_dir / "truth" / "chapter-0004.json").exists()
    assert sorted(path.name for path in (book_dir / "exports").glob("chapter-0004*")) == ["chapter-0004.txt.tmp"]
    assert not list((book_dir / "snapshots").glob("*ch0004*"))
    assert not (book_dir / "chapters" / "0004" / "runs").exists()
    assert (book_dir / "book.json").exists()
    assert storage.read_json(paths.book_meta("book-a"))["current_chapter"] == 4

    assert (backup_dir / "chapters" / "0004.md").read_text(encoding="utf-8") == "第4章正文"
    assert (backup_dir / "plans" / "0004.json").is_file()
    assert json.loads((backup_dir / "truth_db_rows.json").read_text(encoding="utf-8"))[0]["chapter_no"] == 4
    assert (backup_dir / "runs" / "pipeline.jsonl").is_file()
    assert (backup_dir / "state" / "chapter_states.json").is_file()

    pipeline_lines = (book_dir / "runs" / "pipeline.jsonl").read_text(encoding="utf-8").splitlines()
    assert any('"chapter_no": 3' in line for line in pipeline_lines)
    assert not any('"book_id": "book-a"' in line and '"chapter_no": 4' in line for line in pipeline_lines)
    assert any('"book_id": "other-book"' in line and '"chapter_no": 4' in line for line in pipeline_lines)

    state_payload = storage.read_json(paths.chapter_states("book-a"))
    assert "book-a:0004" not in state_payload
    assert "book-a:0003" in state_payload

    assert store.database.query_by_chapter("book-a", 4) == []
    assert len(store.database.query_by_chapter("book-b", 4)) == 2


def test_chapter_discarder_is_idempotent_for_missing_chapter(tmp_path: Path) -> None:
    paths = StoragePaths(tmp_path / "books")
    storage = BookStorage(paths.books_root)
    discarder = ChapterDiscarder(storage, paths)

    result = discarder.discard("missing-book", 9)

    assert result.deleted_files == ()
    assert result.rewritten_files == ()
    assert result.truth_db_rows == 0
    assert result.pipeline_lines_removed == 0
    assert result.state_removed is False


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


def _fingerprint(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()
