from __future__ import annotations

import pytest

from storyforge3.prompts.registry import PromptRegistry, PromptTemplate
from storyforge3.services.prompt_service import PromptService


def template(task_type: str, version: int) -> PromptTemplate:
    return PromptTemplate(
        prompt_id=f"{task_type}-v{version}",
        task_type=task_type,
        version=version,
        role_definition="你是第{chapter_no}章作者",
        constraints=["保持{tone}。", "缺失字段保留为{missing_value}。"],
        output_instruction="只输出正文。",
        generation_config={"temperature": 0.4 + version / 10},
    )


def registry_with_templates() -> PromptRegistry:
    registry = PromptRegistry()
    registry.register(template("compose", 1))
    registry.register(template("compose", 2))
    registry.register(template("plan", 1))
    return registry


def test_get_returns_latest_template_when_version_omitted() -> None:
    service = PromptService(registry_with_templates())

    result = service.get("compose")

    assert result.prompt_id == "compose-v2"
    assert result.version == 2


def test_get_returns_specific_version() -> None:
    service = PromptService(registry_with_templates())

    result = service.get("compose", version=1)

    assert result.prompt_id == "compose-v1"
    assert result.version == 1


def test_render_uses_latest_template_and_replaces_values() -> None:
    service = PromptService(registry_with_templates())

    rendered = service.render("compose", chapter_no=8, tone="冷静克制")

    assert "你是第8章作者" in rendered
    assert "保持冷静克制。" in rendered
    assert "只输出正文。" in rendered


def test_render_keeps_missing_placeholder_visible() -> None:
    service = PromptService(registry_with_templates())

    rendered = service.render("compose", chapter_no=8, tone="冷静克制")

    assert "缺失字段保留为{missing_value}。" in rendered


def test_list_templates_returns_task_types_with_versions() -> None:
    service = PromptService(registry_with_templates())

    result = service.list_templates()

    assert result == [
        {"task_type": "compose", "versions": [1, 2]},
        {"task_type": "plan", "versions": [1]},
    ]


def test_get_missing_task_raises_key_error() -> None:
    service = PromptService(registry_with_templates())

    with pytest.raises(KeyError, match="missing"):
        service.get("missing")


def test_get_missing_version_raises_key_error() -> None:
    service = PromptService(registry_with_templates())

    with pytest.raises(KeyError, match="compose v99"):
        service.get("compose", version=99)
