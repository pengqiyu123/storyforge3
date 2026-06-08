from __future__ import annotations

from html import escape
from pathlib import Path

from ebooklib import epub


def write_epub_book(
    output_path: Path,
    *,
    book_id: str,
    title: str,
    chapters: list[tuple[int, str]],
    author: str = "StoryForge3",
    language: str = "zh-CN",
) -> Path:
    book = epub.EpubBook()
    book.set_identifier(book_id)
    book.set_title(title)
    book.set_language(language)
    book.add_author(author)

    epub_chapters = []
    for chapter_no, text in chapters:
        chapter = epub.EpubHtml(
            title=f"第{chapter_no}章",
            file_name=f"chapter-{chapter_no:04d}.xhtml",
            lang=language,
        )
        chapter.content = _chapter_xhtml(chapter_no, text)
        book.add_item(chapter)
        epub_chapters.append(chapter)

    book.toc = tuple(epub_chapters)
    book.spine = ["nav", *epub_chapters]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    output_path.parent.mkdir(parents=True, exist_ok=True)
    epub.write_epub(str(output_path), book)
    return output_path


def _chapter_xhtml(chapter_no: int, text: str) -> str:
    paragraphs = [part.strip() for part in text.replace("\r\n", "\n").split("\n\n") if part.strip()]
    body = "\n".join(f"<p>{escape(paragraph)}</p>" for paragraph in paragraphs)
    return f"<h1>第{chapter_no}章</h1>\n{body}"
