from __future__ import annotations

import pytest

from storyforge3.audit.context import build_mechanical_context
from storyforge3.audit.runner import AuditRunner
from storyforge3.audit.rules import RULE_REGISTRY
from storyforge3.models import RuleCategory, RuleResult, RuleSeverity


def test_rule_registry_has_36_rules() -> None:
    assert len(RULE_REGISTRY) == 36


@pytest.mark.parametrize("rule_id", sorted(RULE_REGISTRY))
def test_each_rule_returns_result(rule_id: str, sample_chapter_text: str) -> None:
    context = build_mechanical_context(1, sample_chapter_text)
    result = RULE_REGISTRY[rule_id](context)
    assert isinstance(result, RuleResult)
    assert result.rule_id == rule_id


def test_empty_text_is_blocking() -> None:
    result = AuditRunner().run_audit(1, "")
    assert result.passed is False
    assert "empty_text" in result.blocking_issues


def test_short_text_is_blocking() -> None:
    result = AuditRunner().run_audit(1, "林默看了一眼。")
    assert result.passed is False
    assert "below_min_word_count" in result.blocking_issues


def test_warning_does_not_block(sample_chapter_text: str) -> None:
    text = sample_chapter_text + " StoryForge2 artifact snapshot"
    result = AuditRunner().run_audit(1, text)
    assert result.passed is True
    assert "internal_engine_terms" in result.warnings


def test_golden_three_hook_accepts_short_impact_and_abnormal_change() -> None:
    text = (
        "林默的名字，正被墙里的人一下一下敲掉。\n"
        "叩，叩叩。\n"
        "第三下落下，白墙猛地向外鼓起，顶出一枚掌印。"
    )

    result = RULE_REGISTRY["golden_three_hook"](build_mechanical_context(3, text))

    assert result.passed is True
    assert result.severity == RuleSeverity.BLOCKING
    assert result.category == RuleCategory.STRUCTURE
    assert result.detail["score"] >= 2


def test_golden_three_hook_rejects_flat_daily_opening() -> None:
    text = "今天天气不错，林默走在路上，想着下午的考试。"

    result = RULE_REGISTRY["golden_three_hook"](build_mechanical_context(3, text))

    assert result.passed is False
    assert result.detail["score"] == 0
    assert result.detail["paragraph_indices"] == [0]
    assert result.detail["snippet"] == "今天天气不错，林默走在路上，想着下午的考试。"


def test_golden_three_hook_accepts_multiple_legacy_keywords() -> None:
    text = "突然，门后传来异常的声音。"

    result = RULE_REGISTRY["golden_three_hook"](build_mechanical_context(3, text))

    assert result.passed is True
    assert result.detail["keyword_hits"] >= 2


def test_markdown_artifacts_does_not_match_empty_strings() -> None:
    text = "林默的名字，正被墙里的人一下一下敲掉。"

    result = RULE_REGISTRY["markdown_artifacts"](build_mechanical_context(3, text))

    assert result.passed is True
    assert result.detail["observed"] == 0


def test_info_dump_reports_longest_paragraph_location() -> None:
    long_paragraph = "林默" * 230
    text = f"林默推开门。\n\n短段落。\n\n{long_paragraph}"

    result = RULE_REGISTRY["info_dump"](build_mechanical_context(3, text))

    assert result.passed is False
    assert result.detail["paragraph_indices"] == [2]
    assert result.detail["snippet"].startswith("林默林默")
    assert len(result.detail["snippet"]) <= 201


def test_forbidden_patterns_reports_matching_paragraph_location() -> None:
    text = "林默推开门。\n\n以下是本章正文，林默继续向前。\n\n声音停了。"

    result = RULE_REGISTRY["forbidden_patterns"](build_mechanical_context(3, text))

    assert result.passed is False
    assert result.detail["paragraph_indices"] == [1]
    assert result.detail["snippet"] == "以下是本章正文，林默继续向前。"


def test_density_rules_do_not_report_paragraph_location() -> None:
    text = "似乎" * 30 + "林默推开门。"

    result = RULE_REGISTRY["hedge_density"](build_mechanical_context(3, text))

    assert result.passed is False
    assert "paragraph_indices" not in result.detail
