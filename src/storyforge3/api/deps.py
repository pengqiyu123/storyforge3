from __future__ import annotations

from pathlib import Path

from fastapi import Depends

from storyforge3.api.sse import sse_manager as sse_manager
from storyforge3.config import StoryForge3Config
from storyforge3.llm.factory import create_llm_service
from storyforge3.services.book_service import BookService
from storyforge3.services.chapter_service import ChapterService
from storyforge3.services.character_service import CharacterService
from storyforge3.services.daemon_service import DaemonService
from storyforge3.services.export_service import ExportService
from storyforge3.services.volume_service import VolumeService
from storyforge3.services.world_service import WorldService
from storyforge3.prompts.registry import PromptRegistry, create_default_registry
from storyforge3.storage import BookStorage, StoragePaths
from storyforge3.truth.extractor import TruthExtractor
from storyforge3.truth.store import TruthStore


def get_config() -> StoryForge3Config:
    return StoryForge3Config()


def get_paths(config: StoryForge3Config = Depends(get_config)) -> StoragePaths:
    return StoragePaths(Path(config.books_dir))


def get_storage(paths: StoragePaths = Depends(get_paths)) -> BookStorage:
    return BookStorage(paths.books_root)


def get_book_service(
    storage: BookStorage = Depends(get_storage),
    paths: StoragePaths = Depends(get_paths),
) -> BookService:
    return BookService(storage, paths)


def get_llm_service(config: StoryForge3Config = Depends(get_config)):
    return create_llm_service(config)


def get_world_service(
    llm=Depends(get_llm_service),
    storage: BookStorage = Depends(get_storage),
    paths: StoragePaths = Depends(get_paths),
    config: StoryForge3Config = Depends(get_config),
) -> WorldService:
    return WorldService(llm, storage, paths, config)


def get_character_service(
    llm=Depends(get_llm_service),
    storage: BookStorage = Depends(get_storage),
    paths: StoragePaths = Depends(get_paths),
    config: StoryForge3Config = Depends(get_config),
) -> CharacterService:
    return CharacterService(llm, storage, paths, config)


def get_volume_service(
    llm=Depends(get_llm_service),
    storage: BookStorage = Depends(get_storage),
    paths: StoragePaths = Depends(get_paths),
    config: StoryForge3Config = Depends(get_config),
) -> VolumeService:
    return VolumeService(llm, storage, paths, config)


def get_chapter_service(
    config: StoryForge3Config = Depends(get_config),
) -> ChapterService:
    return ChapterService(config)


def get_export_service(
    storage: BookStorage = Depends(get_storage),
    paths: StoragePaths = Depends(get_paths),
) -> ExportService:
    return ExportService(storage, paths)


def get_truth_store(config: StoryForge3Config = Depends(get_config)) -> TruthStore:
    return TruthStore(config.books_dir)


def get_prompt_registry() -> PromptRegistry:
    return create_default_registry()


def get_truth_extractor(
    llm=Depends(get_llm_service),
    registry: PromptRegistry = Depends(get_prompt_registry),
) -> TruthExtractor:
    return TruthExtractor(llm, registry)


def get_daemon_service(
    config: StoryForge3Config = Depends(get_config),
    chapter_service: ChapterService = Depends(get_chapter_service),
    export_service: ExportService = Depends(get_export_service),
) -> DaemonService:
    return DaemonService(config, chapter_service, export_service)
