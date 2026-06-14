from __future__ import annotations

from storyforge3.config import StoryForge3Config
from storyforge3.llm.llm_service import LLMService
from storyforge3.llm.provider_config import ProviderConfigManager, build_provider_from_profile


def create_llm_service(config: StoryForge3Config) -> LLMService:
    manager = ProviderConfigManager(
        config.resolved_providers_config_dir(),
        ccswitch_db_path=config.resolved_ccswitch_db_path(),
    )
    provider = manager.get_active_provider()
    if provider is None:
        return _service(config, {})
    fallback_provider = None
    for profile in manager.list_imported(include_secrets=True):
        if profile.get("provider_key") == provider.get("key"):
            continue
        if profile.get("enabled") and profile.get("api_key"):
            fallback_provider = build_provider_from_profile(profile)
            break
    return _service(config, provider, fallback_provider=fallback_provider)


def _service(config: StoryForge3Config, provider: dict, *, fallback_provider: dict | None = None) -> LLMService:
    return LLMService(
        provider,
        fallback_provider=fallback_provider,
        default_timeout=config.llm_timeout_seconds,
        draft_timeout=config.llm_draft_timeout_seconds,
        truth_timeout=config.llm_truth_timeout_seconds,
        short_timeout=config.llm_short_timeout_seconds,
    )
