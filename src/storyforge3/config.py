from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class StoryForge3Config(BaseSettings):
    """Runtime settings loaded from environment and .env only."""

    # ── Provider config source ─────────────────────────────
    providers_config_dir: str = ".storyforge3"
    llm_timeout_seconds: int = 120
    llm_draft_timeout_seconds: int = 300
    llm_short_timeout_seconds: int = 60
    health_check_on_startup: bool = True

    # ── Model routing ───────────────────────────────────────
    # Empty string = fall back to default_model.
    # Layer 1 (global): CCSwitch switches provider → all tools follow.
    # Layer 2 (per-task): SF3 specifies different model per task through CCSwitch.
    default_model: str = "gpt-4o"
    writer_model: str = ""
    auditor_model: str = ""
    truth_extractor_model: str = ""
    architect_model: str = ""
    planner_model: str = ""

    # ── Storage ─────────────────────────────────────────────
    books_dir: str = "books"

    # ── Snapshots ───────────────────────────────────────────
    snapshot_enabled: bool = True
    snapshot_max_count: int = 5

    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    def model_for_task(self, task_name: str) -> str | None:
        """Resolve task override; None means use CCSwitch current provider model."""
        task_models: dict[str, str] = {
            "writer": self.writer_model,
            "draft": self.writer_model,
            "auditor": self.auditor_model,
            "truth_extractor": self.truth_extractor_model,
            "extract": self.truth_extractor_model,
            "architect": self.architect_model,
            "world_build": self.architect_model,
            "planner": self.planner_model,
            "plan": self.planner_model,
        }
        if task_name in task_models:
            return task_models[task_name] or None
        return self.default_model
