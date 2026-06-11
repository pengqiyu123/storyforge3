from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from storyforge3.config import StoryForge3Config


def make_config(tmp_path: Path) -> StoryForge3Config:
    return StoryForge3Config(books_dir=str(tmp_path / "books"), providers_config_dir=str(tmp_path / ".storyforge3"))


def write_book(root: Path, book_id: str = "lurenjia", text: str = "第一章正文") -> Path:
    book_dir = root / book_id
    (book_dir / "chapters").mkdir(parents=True, exist_ok=True)
    (book_dir / "state").mkdir(parents=True, exist_ok=True)
    (book_dir / "book.json").write_text('{"title":"我是路人甲"}', encoding="utf-8")
    (book_dir / "chapters" / "0001.md").write_text(text, encoding="utf-8")
    (book_dir / "state" / "chapter_states.json").write_text("{}", encoding="utf-8")
    return book_dir


def test_validate_valid_workspace(tmp_path: Path) -> None:
    from storyforge3.services.workspace_service import WorkspaceService

    config = make_config(tmp_path)
    write_book(Path(config.books_dir))

    result = WorkspaceService(config).validate()

    assert result.valid is True
    assert result.book_count == 1
    assert result.issues == ()


def test_validate_missing_workspace_reports_issue_without_creating(tmp_path: Path) -> None:
    from storyforge3.services.workspace_service import WorkspaceService

    config = make_config(tmp_path)

    result = WorkspaceService(config).validate()

    assert result.valid is False
    assert "不存在" in result.issues[0]
    assert not Path(config.books_dir).exists()


def test_validate_path_that_is_not_directory(tmp_path: Path) -> None:
    from storyforge3.services.workspace_service import WorkspaceService

    config = make_config(tmp_path)
    Path(config.books_dir).write_text("not a directory", encoding="utf-8")

    result = WorkspaceService(config).validate()

    assert result.valid is False
    assert "不是目录" in result.issues[0]


def test_validate_not_writable_workspace_reports_issue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from storyforge3.services.workspace_service import WorkspaceService

    config = make_config(tmp_path)
    Path(config.books_dir).mkdir(parents=True)
    original_write_text = Path.write_text

    def fail_write_test(path: Path, *args, **kwargs):
        if path.name == ".sf3_write_test":
            raise OSError("permission denied")
        return original_write_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_write_test)

    result = WorkspaceService(config).validate()

    assert result.valid is False
    assert "不可写" in result.issues[0]


def test_backup_creates_zip_with_books_data(tmp_path: Path) -> None:
    from storyforge3.services.workspace_service import WorkspaceService

    config = make_config(tmp_path)
    write_book(Path(config.books_dir))

    result = WorkspaceService(config).backup()

    backup_path = Path(result.path)
    assert backup_path.exists()
    assert result.book_count == 1
    assert result.size_bytes > 0
    with zipfile.ZipFile(backup_path) as archive:
        assert "lurenjia/book.json" in archive.namelist()
        assert "lurenjia/chapters/0001.md" in archive.namelist()


def test_backup_invalid_workspace_raises_value_error(tmp_path: Path) -> None:
    from storyforge3.services.workspace_service import WorkspaceService

    config = make_config(tmp_path)

    with pytest.raises(ValueError, match="工作区目录不存在"):
        WorkspaceService(config).backup()


def test_restore_valid_zip_replaces_books_and_creates_safety_backup(tmp_path: Path) -> None:
    from storyforge3.services.workspace_service import WorkspaceService

    config = make_config(tmp_path)
    books_dir = Path(config.books_dir)
    write_book(books_dir, text="当前正文")
    incoming = tmp_path / "incoming.zip"
    with zipfile.ZipFile(incoming, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("lurenjia/book.json", '{"title":"恢复版"}')
        archive.writestr("lurenjia/chapters/0001.md", "恢复正文")

    result = WorkspaceService(config).restore(incoming)

    assert result.success is True
    assert result.book_count == 1
    assert "恢复成功" in result.message
    assert Path(result.backup_path).exists()
    assert (books_dir / "lurenjia" / "chapters" / "0001.md").read_text(encoding="utf-8") == "恢复正文"
    with zipfile.ZipFile(result.backup_path) as archive:
        assert archive.read("lurenjia/chapters/0001.md").decode("utf-8") == "当前正文"


def test_restore_invalid_zip_returns_failure_without_modifying_workspace(tmp_path: Path) -> None:
    from storyforge3.services.workspace_service import WorkspaceService

    config = make_config(tmp_path)
    books_dir = Path(config.books_dir)
    write_book(books_dir, text="当前正文")
    incoming = tmp_path / "invalid.zip"
    with zipfile.ZipFile(incoming, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("notes/readme.txt", "no books here")

    result = WorkspaceService(config).restore(incoming)

    assert result.success is False
    assert result.backup_path == ""
    assert (books_dir / "lurenjia" / "chapters" / "0001.md").read_text(encoding="utf-8") == "当前正文"
    assert not list(tmp_path.glob("sf3-backup-*.zip"))


def test_restore_skips_zip_slip_entries(tmp_path: Path) -> None:
    from storyforge3.services.workspace_service import WorkspaceService

    config = make_config(tmp_path)
    books_dir = Path(config.books_dir)
    write_book(books_dir, text="当前正文")
    incoming = tmp_path / "incoming.zip"
    with zipfile.ZipFile(incoming, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("safe/book.json", '{"title":"safe"}')
        archive.writestr("../escape.txt", "danger")
        archive.writestr("/absolute.txt", "danger")

    result = WorkspaceService(config).restore(incoming)

    assert result.success is True
    assert not (tmp_path / "escape.txt").exists()
    assert not (books_dir / "absolute.txt").exists()
