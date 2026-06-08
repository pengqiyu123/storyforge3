from __future__ import annotations

UTF8_BOM = b"\xef\xbb\xbf"


def format_qidian_chapter(chapter_no: int, text: str) -> str:
    return f"第{chapter_no}章\n\n{_normalize_body(text)}"


def format_qidian_book(chapters: list[tuple[int, str]]) -> str:
    return "\n\n***\n\n".join(format_qidian_chapter(chapter_no, text) for chapter_no, text in chapters)


def with_utf8_bom(text: str) -> bytes:
    return UTF8_BOM + text.encode("utf-8")


def _normalize_body(text: str) -> str:
    paragraphs = [part.strip() for part in text.replace("\r\n", "\n").split("\n\n") if part.strip()]
    return "\n\n".join(paragraphs)
