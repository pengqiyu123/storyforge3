from __future__ import annotations

from pathlib import Path

from storyforge3.config import StoryForge3Config


def test_config_defaults() -> None:
    config = StoryForge3Config()
    assert config.providers_config_dir == ".storyforge3"
    assert config.default_model == "gpt-4o"
    assert config.llm_timeout_seconds == 120
    assert config.llm_draft_timeout_seconds == 300
    assert config.llm_truth_timeout_seconds == 600
    assert config.llm_short_timeout_seconds == 60


def test_config_env_override(monkeypatch) -> None:
    monkeypatch.setenv("DEFAULT_MODEL", "gpt-5.5")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "33")
    monkeypatch.setenv("LLM_DRAFT_TIMEOUT_SECONDS", "333")
    monkeypatch.setenv("LLM_TRUTH_TIMEOUT_SECONDS", "444")
    monkeypatch.setenv("LLM_SHORT_TIMEOUT_SECONDS", "44")
    config = StoryForge3Config()
    assert config.default_model == "gpt-5.5"
    assert config.llm_timeout_seconds == 33
    assert config.llm_draft_timeout_seconds == 333
    assert config.llm_truth_timeout_seconds == 444
    assert config.llm_short_timeout_seconds == 44


def test_config_reads_ccswitch_db_path_env(monkeypatch) -> None:
    monkeypatch.setenv("CCSWITCH_DB_PATH", "C:/Users/demo/.cc-switch/cc-switch.db")

    config = StoryForge3Config()

    assert config.ccswitch_db_path == "C:/Users/demo/.cc-switch/cc-switch.db"
    assert config.resolved_ccswitch_db_path() == Path("C:/Users/demo/.cc-switch/cc-switch.db")


def test_windows_ccswitch_db_path_is_not_joined_to_posix_cwd(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CCSWITCH_DB_PATH", "C:/Users/demo/.cc-switch/cc-switch.db")

    config = StoryForge3Config()

    assert config.resolved_ccswitch_db_path() == Path("C:/Users/demo/.cc-switch/cc-switch.db")


def test_default_provider_config_dir_is_stable_across_cwd(monkeypatch, tmp_path) -> None:
    config = StoryForge3Config()
    before = config.resolved_providers_config_dir()
    monkeypatch.chdir(tmp_path)

    after = StoryForge3Config().resolved_providers_config_dir()

    assert before == after
    assert after.name == ".storyforge3"


def test_explicit_provider_config_dir_override_is_respected(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PROVIDERS_CONFIG_DIR", "custom-providers")

    config = StoryForge3Config()

    assert config.resolved_providers_config_dir() == tmp_path / "custom-providers"
