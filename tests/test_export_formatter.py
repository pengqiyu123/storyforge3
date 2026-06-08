from __future__ import annotations

from storyforge3.export.formatter import PlatformFormatter


def test_format_chapter_adds_header_and_strips_markdown() -> None:
    text = "# 标题\n\n**林默**走进副楼。\n\n---\n\n他停下脚步。"
    formatted = PlatformFormatter().format_chapter("异常咨询", 8, text)
    assert formatted.splitlines()[0] == "第8章 异常咨询"
    assert "#" not in formatted
    assert "**" not in formatted
    assert "---" not in formatted


def test_check_format_detects_short_text() -> None:
    errors = PlatformFormatter().check_format("短章", 1, "第1章 短章\n太短。")
    assert "word_count_out_of_range" in errors


def test_check_format_passes_valid_text(sample_chapter_text: str) -> None:
    formatter = PlatformFormatter()
    formatted = formatter.format_chapter("副楼门口", 8, sample_chapter_text)
    assert formatter.check_format("副楼门口", 8, formatted) == []
