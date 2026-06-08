from __future__ import annotations

import dataclasses

import pytest

from storyforge3.models import (
    AuditResult,
    ChapterResult,
    ChapterStatus,
    RuleCategory,
    RuleResult,
    RuleSeverity,
    TruthData,
)


def test_rule_result_is_frozen() -> None:
    result = RuleResult("empty_text", False, RuleSeverity.BLOCKING, RuleCategory.INTEGRITY, "empty")
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.passed = True  # type: ignore[misc]


def test_chapter_result_accepts_optional_audit_and_truth() -> None:
    audit = AuditResult(1, True, (), ("style_warning",), (), ())
    truth = TruthData(1, "runtime_native", ("fact",), (), (), (), (), ())
    result = ChapterResult("book", 1, ChapterStatus.EXPORTED, "标题", "正文", audit=audit, truth=truth)
    assert result.audit is audit
    assert result.truth is truth
