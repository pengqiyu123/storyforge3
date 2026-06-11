from __future__ import annotations

from typing import Any

from storyforge3.config import StoryForge3Config
from storyforge3.llm.factory import create_llm_service
from storyforge3.models import TruthData
from storyforge3.prompts.registry import PromptRegistry, create_default_registry
from storyforge3.truth.extractor import TruthExtractor
from storyforge3.truth.store import TruthStore


class TruthService:
    """Truth 提取、存储、查询的统一服务。"""

    def __init__(
        self,
        *,
        config: StoryForge3Config,
        extractor: Any | None = None,
        store: TruthStore | None = None,
        registry: PromptRegistry | None = None,
    ) -> None:
        self.config = config
        self._store = store or TruthStore(config.books_dir)
        self._registry = registry or create_default_registry()
        self._extractor = extractor

    async def extract(
        self,
        chapter_no: int,
        text: str,
        prev: TruthData | None = None,
    ) -> TruthData:
        """从章节文本提取 truth。"""
        if self._extractor is None:
            self._extractor = TruthExtractor(create_llm_service(self.config), self._registry)
        return await self._extractor.extract(chapter_no, text, prev)

    def save(self, book_id: str, truth: TruthData) -> None:
        """持久化 truth 数据。"""
        self._store.save(book_id, truth)

    def load_latest(self, book_id: str) -> TruthData | None:
        """加载最新章节 truth。"""
        return self._store.load_latest(book_id)

    def load_history(self, book_id: str) -> list[TruthData]:
        """按章节顺序加载所有已持久化 truth。"""
        return self._store.load_history(book_id)
