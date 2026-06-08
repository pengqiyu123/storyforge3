from __future__ import annotations

from dataclasses import dataclass

from storyforge3.audit.chinese_text import count_chinese_chars, split_paragraphs, split_sentences


@dataclass(frozen=True)
class MechanicalContext:
    chapter_no: int
    text: str
    chinese_chars: int
    paragraphs: tuple[str, ...]
    sentences: tuple[str, ...]


def build_mechanical_context(chapter_no: int, text: str) -> MechanicalContext:
    paragraphs = tuple(split_paragraphs(text))
    sentences = tuple(split_sentences(text))
    return MechanicalContext(
        chapter_no=chapter_no,
        text=text,
        chinese_chars=count_chinese_chars(text),
        paragraphs=paragraphs,
        sentences=sentences,
    )
