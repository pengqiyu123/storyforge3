"""Real LLM smoke test. Requires readable CCSwitch config and a working provider."""

from __future__ import annotations

import asyncio

from storyforge3.config import StoryForge3Config
from storyforge3.llm.factory import create_llm_service
from storyforge3.llm.provider_config import ProviderConfigManager


async def main() -> None:
    config = StoryForge3Config()
    manager = ProviderConfigManager(config.providers_config_dir)
    provider = manager.get_active_provider()
    if provider is None:
        raise SystemExit(f"No active imported provider in {manager.config_path}")

    print(f"当前 provider: {provider['label']}")
    print(f"Base URL: {provider['base_url']}")
    print(f"Model: {provider['model_id']}")

    result = await create_llm_service(config).generate_text(
        task_name="test",
        system_prompt="你是一个网文创作助手。",
        user_payload={"task": "用一句话描述一个都市玄幻的设定"},
        model=provider["model_id"],
    )
    print(f"\n生成结果:\n{result}")


if __name__ == "__main__":
    asyncio.run(main())
