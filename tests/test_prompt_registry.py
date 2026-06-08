from __future__ import annotations

import pytest

from storyforge3.prompts.registry import PromptRegistry, PromptTemplate, create_default_registry


def template(version: int) -> PromptTemplate:
    return PromptTemplate("compose-v1", "compose", version, "你是作者", ["写第{chapter_no}章"], "只输出正文", {}, "2026-06-01")


def test_registry_get_latest() -> None:
    registry = PromptRegistry()
    registry.register(template(1))
    registry.register(template(2))
    assert registry.get_latest("compose").version == 2


def test_registry_get_version() -> None:
    registry = PromptRegistry()
    registry.register(template(1))
    assert registry.get_version("compose", 1).version == 1


def test_registry_missing_version_raises() -> None:
    with pytest.raises(KeyError):
        PromptRegistry().get_latest("missing")


def test_render_replaces_variables() -> None:
    registry = PromptRegistry()
    rendered = registry.render_system_prompt(template(1), chapter_no=8)
    assert "写第8章" in rendered
    assert "只输出正文" in rendered


def test_default_registry_has_three_templates() -> None:
    registry = create_default_registry()
    assert {"compose", "truth_extract", "audit"}.issubset(set(registry.list_task_types()))


def test_default_registry_has_dedicated_plan_template() -> None:
    registry = create_default_registry()
    template = registry.get_latest("plan")
    rendered = registry.render_system_prompt(template, chapter_no=8)

    assert template.prompt_id == "plan-v1"
    assert template.generation_config["temperature"] == 0.5
    assert "规划第8章" in rendered
    assert "不要输出章节正文" in rendered


def test_truth_extract_latest_template_declares_required_schema() -> None:
    registry = create_default_registry()
    template = registry.get_latest("truth_extract")
    rendered = registry.render_system_prompt(template, chapter_no=8)

    assert template.prompt_id == "truth-extract-v2"
    assert "fact_assertions" in rendered
    assert "必填" in rendered
    assert "character_updates" in rendered
    assert "relationship_updates" in rendered
    assert "hook_updates" in rendered
    assert "irreversible_facts" in rendered
    assert "notes" in rendered
