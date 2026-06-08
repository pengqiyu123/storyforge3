from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from ebooklib import epub

from storyforge3.config import StoryForge3Config
from storyforge3.models import ChapterStatus
from storyforge3.services.chapter_service import ChapterService
from storyforge3.services.export_service import ExportService
from storyforge3.state.machine import ChapterStateMachine
from storyforge3.storage import BookStorage, StoragePaths


def run(coro):
    return asyncio.run(coro)


def write_book(root: Path, title: str = "我是路人甲") -> None:
    (root / "book.json").write_text(
        (
            "{"
            '"book_id":"lurenjia",'
            f'"title":"{title}",'
            '"genre":"urban",'
            '"platform":"tomato",'
            '"status":"active",'
            '"target_chapters":10,'
            '"chapter_word_count":2000,'
            '"language":"zh",'
            '"current_chapter":2,'
            '"created_at":"",'
            '"updated_at":""'
            "}"
        ),
        encoding="utf-8",
    )


def write_chapter(root: Path, chapter_no: int, text: str) -> None:
    path = root / "chapters" / f"{chapter_no:04d}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def approve_chapter(paths: StoragePaths, book_id: str, chapter_no: int) -> None:
    machine = ChapterStateMachine(paths.chapter_states(book_id))
    machine.advance(book_id, chapter_no, ChapterStatus.PLANNED)
    machine.advance(book_id, chapter_no, ChapterStatus.DRAFTED)
    machine.advance(book_id, chapter_no, ChapterStatus.AUDITED)
    machine.advance(book_id, chapter_no, ChapterStatus.APPROVED)


@pytest.fixture
def export_workspace(config: StoryForge3Config) -> tuple[BookStorage, StoragePaths, Path]:
    paths = StoragePaths(Path(config.books_dir))
    storage = BookStorage(paths.books_root)
    root = paths.book_dir("lurenjia")
    root.mkdir(parents=True)
    write_book(root)
    write_chapter(root, 1, "林默站在检测中心门口。\n\n许青把记录表递给他。")
    write_chapter(root, 2, "周砚推开诊室的门。\n\n门里的灯忽然暗了一下。")
    return storage, paths, root


def test_export_book_markdown_collection(config: StoryForge3Config, export_workspace) -> None:
    storage, paths, _root = export_workspace
    approve_chapter(paths, "lurenjia", 1)
    approve_chapter(paths, "lurenjia", 2)
    service = ExportService(storage, paths)

    path = run(service.export_book("lurenjia", "md"))

    assert path.name == "lurenjia.md"
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# 我是路人甲\n\n")
    assert "## 第1章" in text
    assert "## 第2章" in text
    assert "林默站在检测中心门口。\n\n许青把记录表递给他。\n\n\n\n## 第2章" in text


def test_export_book_qidian_txt_has_bom_and_separator(config: StoryForge3Config, export_workspace) -> None:
    storage, paths, _root = export_workspace
    approve_chapter(paths, "lurenjia", 1)
    approve_chapter(paths, "lurenjia", 2)
    service = ExportService(storage, paths)

    path = run(service.export_book("lurenjia", "qidian_txt"))

    raw = path.read_bytes()
    assert path.name == "lurenjia-qidian.txt"
    assert raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    assert "第1章\n\n林默站在检测中心门口。" in text
    assert "\n\n***\n\n第2章\n\n周砚推开诊室的门。" in text


def test_export_book_epub_is_parseable_with_toc(config: StoryForge3Config, export_workspace) -> None:
    storage, paths, _root = export_workspace
    approve_chapter(paths, "lurenjia", 1)
    approve_chapter(paths, "lurenjia", 2)
    service = ExportService(storage, paths)

    path = run(service.export_book("lurenjia", "epub"))

    book = epub.read_epub(str(path))
    docs = [item for item in book.get_items() if item.get_name().startswith("chapter-")]
    assert path.name == "lurenjia.epub"
    assert book.get_metadata("DC", "title")[0][0] == "我是路人甲"
    assert book.get_metadata("DC", "language")[0][0] == "zh-CN"
    assert len(docs) == 2
    assert len(book.toc) == 2


def test_export_book_filters_unapproved_chapters_by_default(config: StoryForge3Config, export_workspace) -> None:
    storage, paths, _root = export_workspace
    approve_chapter(paths, "lurenjia", 1)
    service = ExportService(storage, paths)

    approved_path = run(service.export_book("lurenjia", "md"))
    approved_text = approved_path.read_text(encoding="utf-8")
    all_path = run(service.export_book("lurenjia", "md", approved_only=False))

    all_text = all_path.read_text(encoding="utf-8")
    assert "## 第1章" in approved_text
    assert "## 第2章" not in approved_text
    assert "## 第2章" in all_text


def test_export_service_rejects_unknown_format(config: StoryForge3Config, export_workspace) -> None:
    storage, paths, _root = export_workspace
    service = ExportService(storage, paths)

    with pytest.raises(ValueError, match="unsupported export format"):
        run(service.export_book("lurenjia", "docx"))


def test_chapter_service_routes_new_export_formats(config: StoryForge3Config, export_workspace) -> None:
    storage, paths, _root = export_workspace
    service = ChapterService(config, storage=storage, paths=paths)

    md_path = run(service.export("lurenjia", 1, "md"))
    qidian_path = run(service.export("lurenjia", 1, "qidian_txt"))

    assert md_path.name == "chapter-0001.md"
    assert qidian_path.name == "chapter-0001-qidian.txt"
    assert md_path.read_text(encoding="utf-8").startswith("## 第1章\n\n")
    assert qidian_path.read_bytes().startswith(b"\xef\xbb\xbf")
