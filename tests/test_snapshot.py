from __future__ import annotations

import asyncio
import json
import zipfile
from pathlib import Path

from storyforge3.config import StoryForge3Config
from storyforge3.models import ChapterStatus
from storyforge3.workflow import ChapterWorkflow

from tests.test_workflow import MockClient, valid_chapter_text


def run(coro):
    return asyncio.run(coro)


def write_snapshot_workspace(root: Path) -> None:
    (root / "chapters").mkdir(parents=True, exist_ok=True)
    (root / "truth").mkdir(parents=True, exist_ok=True)
    (root / "state").mkdir(parents=True, exist_ok=True)
    (root / "book.json").write_text('{"title":"我是路人甲"}', encoding="utf-8")
    (root / "world.json").write_text('{"setting":"现代都市"}', encoding="utf-8")
    (root / "characters.json").write_text('{"characters":[]}', encoding="utf-8")
    (root / "volumes.json").write_text('{"volumes":[]}', encoding="utf-8")
    (root / "context.md").write_text("主角林默，能力是存在感调节。", encoding="utf-8")
    (root / "chapters" / "0001.md").write_text("第一章正文", encoding="utf-8")
    (root / "truth" / "chapter-0001.json").write_text(
        json.dumps(
            {
                "chapter_no": 1,
                "source": "runtime_native",
                "fact_assertions": ["事实"],
                "character_updates": [],
                "relationship_updates": [],
                "hook_updates": [],
                "irreversible_facts": [],
                "notes": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (root / "state" / "snapshot.json").write_text('{"ok":true}', encoding="utf-8")


def zip_names(path: Path) -> set[str]:
    with zipfile.ZipFile(path) as archive:
        return set(archive.namelist())


def test_config_snapshot_defaults() -> None:
    config = StoryForge3Config()

    assert config.snapshot_enabled is True
    assert config.snapshot_max_count == 5


def test_create_snapshot_zip_exists(tmp_path: Path) -> None:
    from storyforge3.snapshot import SnapshotManager

    write_snapshot_workspace(tmp_path / "lurenjia")

    path = SnapshotManager(tmp_path).create_snapshot("lurenjia", 1)

    assert path is not None
    assert path.exists()
    assert path.suffix == ".zip"


def test_create_snapshot_contains_chapters(tmp_path: Path) -> None:
    from storyforge3.snapshot import SnapshotManager

    write_snapshot_workspace(tmp_path / "lurenjia")

    path = SnapshotManager(tmp_path).create_snapshot("lurenjia", 1)

    assert path is not None
    assert "chapters/0001.md" in zip_names(path)


def test_create_snapshot_contains_truth_and_state(tmp_path: Path) -> None:
    from storyforge3.snapshot import SnapshotManager

    write_snapshot_workspace(tmp_path / "lurenjia")
    (tmp_path / "truth.db").write_bytes(b"sqlite bytes")
    (tmp_path / "state.json").write_text('{"lurenjia:0001":{"status":"approved","history":[]}}', encoding="utf-8")

    path = SnapshotManager(tmp_path).create_snapshot("lurenjia", 1)

    assert path is not None
    names = zip_names(path)
    assert "truth/chapter-0001.json" in names
    assert "truth.db" in names
    assert "state/snapshot.json" in names
    assert "state/state.json" in names


def test_create_snapshot_metadata(tmp_path: Path) -> None:
    from storyforge3.snapshot import SnapshotManager

    write_snapshot_workspace(tmp_path / "lurenjia")

    path = SnapshotManager(tmp_path).create_snapshot("lurenjia", 7)

    assert path is not None
    meta = json.loads(path.with_suffix(".meta.json").read_text(encoding="utf-8"))
    assert meta["book_id"] == "lurenjia"
    assert meta["chapter_no"] == 7
    assert meta["timestamp"]
    assert meta["file_count"] >= 7


def test_list_snapshots_ordered(tmp_path: Path) -> None:
    from storyforge3.snapshot import SnapshotManager

    write_snapshot_workspace(tmp_path / "lurenjia")
    manager = SnapshotManager(tmp_path)
    for chapter_no in range(1, 4):
        manager.create_snapshot("lurenjia", chapter_no)

    snapshots = manager.list_snapshots("lurenjia")

    assert [item["chapter_no"] for item in snapshots] == [3, 2, 1]


def test_cleanup_removes_oldest(tmp_path: Path) -> None:
    from storyforge3.snapshot import SnapshotManager

    write_snapshot_workspace(tmp_path / "lurenjia")
    manager = SnapshotManager(tmp_path, max_count=2)
    for chapter_no in range(1, 4):
        manager.create_snapshot("lurenjia", chapter_no)

    snapshots = manager.list_snapshots("lurenjia")

    assert [item["chapter_no"] for item in snapshots] == [3, 2]
    assert len(list((tmp_path / "lurenjia" / "snapshots").glob("*.zip"))) == 2


def test_cleanup_removes_paired_meta(tmp_path: Path) -> None:
    from storyforge3.snapshot import SnapshotManager

    write_snapshot_workspace(tmp_path / "lurenjia")
    manager = SnapshotManager(tmp_path, max_count=2)
    for chapter_no in range(1, 4):
        manager.create_snapshot("lurenjia", chapter_no)

    snap_dir = tmp_path / "lurenjia" / "snapshots"

    assert len(list(snap_dir.glob("*.zip"))) == 2
    assert len(list(snap_dir.glob("*.meta.json"))) == 2


def test_snapshot_empty_book_returns_none(tmp_path: Path) -> None:
    from storyforge3.snapshot import SnapshotManager

    (tmp_path / "empty").mkdir()

    assert SnapshotManager(tmp_path).create_snapshot("empty", 1) is None


def test_snapshot_nonexistent_book_returns_none(tmp_path: Path) -> None:
    from storyforge3.snapshot import SnapshotManager

    assert SnapshotManager(tmp_path).create_snapshot("missing", 1) is None


def test_restore_snapshot_restores_only_chapters_and_state(tmp_path: Path) -> None:
    from storyforge3.snapshot import SnapshotManager

    root = tmp_path / "lurenjia"
    write_snapshot_workspace(root)
    manager = SnapshotManager(tmp_path)
    snapshot = manager.create_snapshot("lurenjia", 1)
    assert snapshot is not None

    (root / "chapters" / "0001.md").write_text("被覆盖的正文", encoding="utf-8")
    (root / "state" / "snapshot.json").write_text('{"ok":false}', encoding="utf-8")
    original_truth = (root / "truth" / "chapter-0001.json").read_text(encoding="utf-8")
    (root / "truth" / "chapter-0001.json").write_text('{"changed":true}', encoding="utf-8")

    result = manager.restore_snapshot("lurenjia", snapshot.name)

    assert result["count"] == 2
    assert set(result["restored_files"]) == {"chapters/0001.md", "state/snapshot.json"}
    assert (root / "chapters" / "0001.md").read_text(encoding="utf-8") == "第一章正文"
    assert (root / "state" / "snapshot.json").read_text(encoding="utf-8") == '{"ok":true}'
    assert (root / "truth" / "chapter-0001.json").read_text(encoding="utf-8") == '{"changed":true}'
    assert (root / "truth" / "chapter-0001.json").read_text(encoding="utf-8") != original_truth


def test_restore_snapshot_skips_zip_slip_and_non_whitelisted_entries(tmp_path: Path) -> None:
    from storyforge3.snapshot import SnapshotManager

    root = tmp_path / "lurenjia"
    snap_dir = root / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    snapshot = snap_dir / "20260610T000000000000Z_ch0001.zip"
    with zipfile.ZipFile(snapshot, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("chapters/0001.md", "安全正文")
        archive.writestr("../escape.txt", "危险")
        archive.writestr("/absolute.txt", "危险")
        archive.writestr("truth/chapter-0001.json", '{"fact":"不该恢复"}')

    result = SnapshotManager(tmp_path).restore_snapshot("lurenjia", snapshot.name)

    assert result["restored_files"] == ["chapters/0001.md"]
    assert (root / "chapters" / "0001.md").read_text(encoding="utf-8") == "安全正文"
    assert not (tmp_path / "escape.txt").exists()
    assert not (root / "truth" / "chapter-0001.json").exists()


def test_restore_snapshot_missing_raises_file_not_found(tmp_path: Path) -> None:
    from storyforge3.snapshot import SnapshotManager

    try:
        SnapshotManager(tmp_path).restore_snapshot("lurenjia", "missing.zip")
    except FileNotFoundError as exc:
        assert "snapshot not found" in str(exc)
    else:
        raise AssertionError("expected missing snapshot")


class SnapshotCheckingWorkflow(ChapterWorkflow):
    async def step_export(self, chapter_no: int, title: str, text: str, book_id: str) -> Path:
        snap_dir = Path(self.config.books_dir) / book_id / "snapshots"
        assert list(snap_dir.glob("*.zip"))
        return await super().step_export(chapter_no, title, text, book_id)


def test_workflow_creates_snapshot_before_export(config, book_workspace: Path) -> None:
    write_snapshot_workspace(book_workspace)
    workflow = SnapshotCheckingWorkflow(config, client=MockClient(valid_chapter_text(1000)))

    result = run(workflow.run("lurenjia", 8, human_confirm=lambda _: True))

    assert result.status == ChapterStatus.EXPORTED
    snap_dir = book_workspace / "snapshots"
    [snapshot] = list(snap_dir.glob("*.zip"))
    assert zipfile.is_zipfile(snapshot)


def test_snapshot_failure_does_not_block_export(config, book_workspace: Path, monkeypatch) -> None:
    from storyforge3 import snapshot

    write_snapshot_workspace(book_workspace)

    def fail_create_snapshot(self, book_id: str, chapter_no: int):
        raise OSError("snapshot disk unavailable")

    monkeypatch.setattr(snapshot.SnapshotManager, "create_snapshot", fail_create_snapshot)
    workflow = ChapterWorkflow(config, client=MockClient(valid_chapter_text(1000)))

    result = run(workflow.run("lurenjia", 8, human_confirm=lambda _: True))

    assert result.status == ChapterStatus.EXPORTED
