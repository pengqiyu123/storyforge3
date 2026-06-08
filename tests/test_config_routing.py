from __future__ import annotations

from storyforge3.config import StoryForge3Config


def test_model_for_task_falls_back_to_default() -> None:
    config = StoryForge3Config(default_model="base-model")
    assert config.model_for_task("writer") is None
    assert config.model_for_task("unknown") == "base-model"


def test_model_for_task_uses_specific_route() -> None:
    config = StoryForge3Config(
        default_model="base-model",
        writer_model="writer-model",
        auditor_model="audit-model",
        truth_extractor_model="truth-model",
        architect_model="architect-model",
        planner_model="planner-model",
    )
    assert config.model_for_task("draft") == "writer-model"
    assert config.model_for_task("auditor") == "audit-model"
    assert config.model_for_task("truth_extractor") == "truth-model"
    assert config.model_for_task("world_build") == "architect-model"
    assert config.model_for_task("plan") == "planner-model"
