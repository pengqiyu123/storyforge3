from __future__ import annotations

from fastapi import APIRouter, Depends

from storyforge3.api.deps import get_config
from storyforge3.api.response import ok
from storyforge3.config import StoryForge3Config

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(config: StoryForge3Config = Depends(get_config)):
    """Return local service status without touching the LLM provider."""
    return ok(
        {
            "status": "ok",
            "default_model": config.default_model,
            "books_dir": config.books_dir,
        }
    )
