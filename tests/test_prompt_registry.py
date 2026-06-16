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


def test_default_registry_contains_only_active_templates() -> None:
    registry = create_default_registry()
    assert set(registry.list_task_types()) == {
        "compose",
        "llm_audit",
        "plan",
        "revise",
        "short_draft",
        "short_plan",
        "truth_extract",
    }


def test_default_registry_has_dedicated_plan_template() -> None:
    registry = create_default_registry()
    template = registry.get_latest("plan")
    rendered = registry.render_system_prompt(template, chapter_no=8)

    assert template.prompt_id == "plan-v2"
    assert template.version == 2
    assert template.generation_config["temperature"] == 0.5
    assert "钩子账" in rendered
    assert "### 本章目标" in rendered
    assert "不要输出正文" in rendered


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
    assert "action 字段" in rendered
    assert "planted/advanced/resolved" in rendered
    assert "irreversible_facts" in rendered
    assert "notes" in rendered


def test_compose_template_includes_continuity_constraints() -> None:
    registry = create_default_registry()
    template = registry.get_latest("compose")
    rendered = registry.render_system_prompt(template, chapter_no=8)

    assert template.prompt_id == "compose-v2"
    assert template.version == 2
    assert "上一章具体动作" in rendered
    assert "写作铁律" in rendered
    assert "看点密集度" in rendered
    assert "断章规则" in rendered
    assert "去 AI 味铁律" in rendered
    assert "逻辑自洽" in rendered


def test_render_warns_for_missing_placeholders() -> None:
    registry = PromptRegistry()
    with pytest.warns(UserWarning, match="Prompt placeholder 'chapter_no' not found"):
        rendered = registry.render_system_prompt(template(1))

    assert "写第{chapter_no}章" in rendered
