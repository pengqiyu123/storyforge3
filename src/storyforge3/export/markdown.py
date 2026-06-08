from __future__ import annotations


def format_markdown_chapter(chapter_no: int, text: str) -> str:
    return f"## 第{chapter_no}章\n\n{_normalize_body(text)}"


def format_markdown_book(title: str, chapters: list[tuple[int, str]]) -> str:
    parts = [f"# {title}"]
    parts.extend(format_markdown_chapter(chapter_no, text) for chapter_no, text in chapters)
    return "\n\n\n\n".join(parts)


def _normalize_body(text: str) -> str:
    paragraphs = [part.strip() for part in text.replace("\r\n", "\n").split("\n\n") if part.strip()]
    return "\n\n".join(paragraphs)
