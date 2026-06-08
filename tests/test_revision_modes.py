from __future__ import annotations

import asyncio

import pytest

from storyforge3.audit.revision_modes import RevisionMode, RevisionModeRecommender, get_mode_config
from storyforge3.config import StoryForge3Config
from storyforge3.models import RuleCategory, RuleResult, RuleSeverity
from storyforge3.prompts.registry import create_default_registry
from storyforge3.services.chapter_service import ChapterService


def run(coro):
    return asyncio.run(coro)


def failed_rule(rule_id: str, category: RuleCategory, severity: RuleSeverity = RuleSeverity.WARNING) -> RuleResult:
    return RuleResult(rule_id, False, severity, category, "failed")


def test_mode_config_anti_detect_has_higher_temperature() -> None:
    config = get_mode_config(RevisionMode.ANTI_DETECT)
    assert config.generation_config_overrides["temperature"] == 0.9
    assert config.allowed_rule_categories == ("ai_tell",)


def test_recommender_all_ai_tell_uses_anti_detect() -> None:
    result = RevisionModeRecommender().recommend(
        [failed_rule("didactic_words", RuleCategory.AI_TELL)],
        blocking_count=0,
        revision_round=0,
    )
    assert result == RevisionMode.ANTI_DETECT


def test_recommender_two_nonblocking_structure_style_uses_spot_fix() -> None:
    result = RevisionModeRecommender().recommend(
        [
            failed_rule("pacing_flat", RuleCategory.STRUCTURE),
            failed_rule("action_sentence_ratio", RuleCategory.STYLE),
        ],
        blocking_count=0,
        revision_round=0,
    )
    assert result == RevisionMode.SPOT_FIX


def test_recommender_blocking_golden_three_hook_uses_spot_fix_with_production_category() -> None:
    result = RevisionModeRecommender().recommend(
        [failed_rule("golden_three_hook", RuleCategory.STRUCTURE, RuleSeverity.BLOCKING)],
        blocking_count=1,
        revision_round=0,
    )
    assert result == RevisionMode.SPOT_FIX


def test_recommender_unbalanced_quote_uses_spot_fix() -> None:
    result = RevisionModeRecommender().recommend(
        [failed_rule("unbalanced_quote_or_bracket", RuleCategory.STRUCTURE, RuleSeverity.BLOCKING)],
        blocking_count=1,
        revision_round=0,
    )
    assert result == RevisionMode.SPOT_FIX


@pytest.mark.parametrize(
    ("rule_id", "category", "expected"),
    [
        ("empty_text", RuleCategory.INTEGRITY, RevisionMode.REWORK),
        ("below_min_word_count", RuleCategory.INTEGRITY, RevisionMode.SURGICAL),
        ("unbalanced_quote_or_bracket", RuleCategory.INTEGRITY, RevisionMode.SPOT_FIX),
        ("forbidden_patterns", RuleCategory.META, RevisionMode.SPOT_FIX),
        ("golden_three_hook", RuleCategory.STRUCTURE, RevisionMode.SPOT_FIX),
    ],
)
def test_recommender_routes_blocking_rules_by_fix_scope(
    rule_id: str,
    category: RuleCategory,
    expected: RevisionMode,
) -> None:
    result = RevisionModeRecommender().recommend(
        [failed_rule(rule_id, category, RuleSeverity.BLOCKING)],
        blocking_count=1,
        revision_round=0,
    )
    assert result == expected


def test_recommender_empty_text_combination_still_uses_rework() -> None:
    result = RevisionModeRecommender().recommend(
        [
            failed_rule("empty_text", RuleCategory.INTEGRITY, RuleSeverity.BLOCKING),
            failed_rule("golden_three_hook", RuleCategory.STRUCTURE, RuleSeverity.BLOCKING),
        ],
        blocking_count=2,
        revision_round=0,
    )
    assert result == RevisionMode.REWORK


def test_recommender_multiple_local_blocking_rules_use_surgical() -> None:
    result = RevisionModeRecommender().recommend(
        [
            failed_rule("unbalanced_quote_or_bracket", RuleCategory.INTEGRITY, RuleSeverity.BLOCKING),
            failed_rule("forbidden_patterns", RuleCategory.META, RuleSeverity.BLOCKING),
            failed_rule("golden_three_hook", RuleCategory.STRUCTURE, RuleSeverity.BLOCKING),
        ],
        blocking_count=3,
        revision_round=0,
    )
    assert result == RevisionMode.SURGICAL


def test_recommender_style_only_uses_polish() -> None:
    result = RevisionModeRecommender().recommend(
        [failed_rule("repeated_phrase", RuleCategory.STYLE)],
        blocking_count=0,
        revision_round=0,
    )
    assert result == RevisionMode.POLISH


def test_recommender_mixed_many_warnings_uses_surgical() -> None:
    result = RevisionModeRecommender().recommend(
        [
            failed_rule("didactic_words", RuleCategory.AI_TELL),
            failed_rule("pacing_flat", RuleCategory.STRUCTURE),
            failed_rule("repeated_phrase", RuleCategory.STYLE),
        ],
        blocking_count=0,
        revision_round=0,
    )
    assert result == RevisionMode.SURGICAL


def test_categorize_failures_groups_rule_ids() -> None:
    grouped = RevisionModeRecommender().categorize_failures(
        [
            failed_rule("didactic_words", RuleCategory.AI_TELL),
            failed_rule("pacing_flat", RuleCategory.STRUCTURE),
        ]
    )
    assert grouped["ai_tell"] == ("didactic_words",)
    assert grouped["structure"] == ("pacing_flat",)


def test_default_registry_registers_revision_prompt() -> None:
    registry = create_default_registry()
    template = registry.get_latest("revise")
    rendered = registry.render_system_prompt(template, mode="anti-detect", failed_rules="didactic_words")
    assert "anti-detect" in rendered
    assert "didactic_words" in rendered


def test_chapter_service_revise_records_auto_mode(config: StoryForge3Config, book_workspace) -> None:
    service = ChapterService(config)
    result = run(service.revise("lurenjia", 7))
    assert result.audit is not None
    assert result.error is not None
    assert "revision_mode=" in result.error
    assert "mode_source=auto_recommended" in result.error


def test_chapter_service_revise_respects_manual_mode(config: StoryForge3Config, book_workspace) -> None:
    service = ChapterService(config)
    result = run(service.revise("lurenjia", 7, mode="polish"))
    assert result.error is not None
    assert "revision_mode=polish" in result.error
    assert "mode_source=manual" in result.error
