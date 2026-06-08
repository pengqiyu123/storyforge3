from __future__ import annotations

from storyforge3.audit.revision_patch import (
    PatchApplyResult,
    TextPatch,
    apply_patches,
    build_patch_targets,
    validate_patch_response,
)
from storyforge3.models import RuleCategory, RuleResult, RuleSeverity


def failed_rule(rule_id: str, category: RuleCategory = RuleCategory.STRUCTURE) -> RuleResult:
    return RuleResult(rule_id, False, RuleSeverity.BLOCKING, category, "failed")


def test_apply_patches_keeps_partial_successes() -> None:
    text = "第一段没有门。\n\n第二段含有作为AI。"
    result = apply_patches(
        text,
        (
            TextPatch("第一段没有门。", "门外传来异常声音，第一段没有门。", "golden_three_hook"),
            TextPatch("不存在的原文", "替换", "forbidden_patterns"),
        ),
    )

    assert isinstance(result, PatchApplyResult)
    assert result.applied_count == 1
    assert result.failed_count == 1
    assert "门外传来异常声音" in result.text
    assert result.failures[0].rule_id == "forbidden_patterns"


def test_apply_patches_fails_when_no_patch_matches() -> None:
    result = apply_patches("原文", (TextPatch("找不到", "替换", "unknown_rule"),))

    assert result.applied_count == 0
    assert result.failed_count == 1
    assert result.text == "原文"


def test_validate_patch_response_accepts_patch_list() -> None:
    patches = validate_patch_response(
        {
            "patches": [
                {"find": "作为AI", "replace": "陈野", "rule_id": "forbidden_patterns"},
                {"find": "旧段落", "replace": "新段落"},
            ]
        }
    )

    assert patches == (
        TextPatch("作为AI", "陈野", "forbidden_patterns"),
        TextPatch("旧段落", "新段落", ""),
    )


def test_build_patch_targets_uses_known_hook_window() -> None:
    text = "第一段平铺。\n\n第二段平铺。\n\n第三段平铺。\n\n第四段不要出现。"
    targets = build_patch_targets(text, [failed_rule("golden_three_hook")])

    assert len(targets) == 1
    assert targets[0].rule_id == "golden_three_hook"
    assert "第一段平铺" in targets[0].window_text
    assert "第三段平铺" in targets[0].window_text
    assert "第四段不要出现" not in targets[0].window_text


def test_golden_three_hook_patch_target_explains_detection_dimensions() -> None:
    text = "第一段平铺。\n\n第二段平铺。\n\n第三段平铺。"
    targets = build_patch_targets(text, [failed_rule("golden_three_hook")])

    allowed_change = targets[0].allowed_change
    assert "至少满足以下两种" in allowed_change
    assert "≤10字的短句冲击段" in allowed_change
    assert "异常/变化词" in allowed_change
    assert "对话引号或拟声词" in allowed_change
    assert "悬念标点" in allowed_change


def test_build_patch_targets_unknown_rule_falls_back_to_keyword_window() -> None:
    text = "第一段正常。\n\n第二段含有特殊关键词。\n\n第三段正常。"
    targets = build_patch_targets(
        text,
        [
            RuleResult(
                "future_rule",
                False,
                RuleSeverity.WARNING,
                RuleCategory.STYLE,
                "failed",
                {"keywords": ["特殊关键词"]},
            )
        ],
    )

    assert len(targets) == 1
    assert targets[0].rule_id == "future_rule"
    assert "第二段含有特殊关键词" in targets[0].window_text
