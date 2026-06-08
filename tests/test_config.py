from __future__ import annotations

from storyforge3.config import StoryForge3Config


def test_config_defaults() -> None:
    config = StoryForge3Config()
    assert config.providers_config_dir == ".storyforge3"
    assert config.default_model == "gpt-4o"
    assert config.llm_timeout_seconds == 120
    assert config.llm_draft_timeout_seconds == 300
    assert config.llm_short_timeout_seconds == 60


def test_config_env_override(monkeypatch) -> None:
    monkeypatch.setenv("DEFAULT_MODEL", "gpt-5.5")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "33")
    monkeypatch.setenv("LLM_DRAFT_TIMEOUT_SECONDS", "333")
    monkeypatch.setenv("LLM_SHORT_TIMEOUT_SECONDS", "44")
    config = StoryForge3Config()
    assert config.default_model == "gpt-5.5"
    assert config.llm_timeout_seconds == 33
    assert config.llm_draft_timeout_seconds == 333
    assert config.llm_short_timeout_seconds == 44
