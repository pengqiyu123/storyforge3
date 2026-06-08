from __future__ import annotations

import re

from storyforge3.audit.chinese_text import count_chinese_chars


class PlatformFormatter:
    def format_chapter(self, title: str, chapter_no: int, source_md_text: str) -> str:
        paragraphs = []
        for raw in re.split(r"\n\s*\n|[\r\n]+", source_md_text):
            cleaned = self._clean_markdown(raw.strip())
            if cleaned:
                paragraphs.append(cleaned)
        return "\n\n".join([f"第{chapter_no}章 {title}", *paragraphs])

    def check_format(self, title: str, chapter_no: int, formatted_text: str) -> list[str]:
        errors: list[str] = []
        lines = formatted_text.splitlines()
        if not lines or lines[0] != f"第{chapter_no}章 {title}":
            errors.append("chapter_header_format")
        if any(pattern in formatted_text for pattern in ("#", "**", "---", "[](", "](")):
            errors.append("markdown_artifacts")
        count = count_chinese_chars(formatted_text)
        if count < 1000 or count > 4000:
            errors.append("word_count_out_of_range")
        paragraphs = [line for line in lines[1:] if line.strip()]
        if len(paragraphs) < 3:
            errors.append("paragraph_count")
        return errors

    @staticmethod
    def _clean_markdown(text: str) -> str:
        text = re.sub(r"^#{1,6}\s*", "", text)
        text = text.replace("**", "")
        text = text.replace("---", "")
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        return text.strip()
