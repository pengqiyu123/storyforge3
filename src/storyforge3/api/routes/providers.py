from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends

from storyforge3.api.deps import get_config, get_llm_service
from storyforge3.api.response import ok
from storyforge3.config import StoryForge3Config
from storyforge3.llm.provider_config import ProviderConfigManager

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("")
async def list_providers(config: StoryForge3Config = Depends(get_config)):
    manager = ProviderConfigManager(Path(config.providers_config_dir))
    return ok(manager.list_imported())


@router.get("/health")
async def provider_health(llm=Depends(get_llm_service)):
    healthy = await llm.check_health()
    return ok({"healthy": healthy})
