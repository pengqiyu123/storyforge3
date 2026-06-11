from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from collections.abc import AsyncGenerator
from typing import Literal

from pydantic import BaseModel


class PipelineEvent(BaseModel):
    """Pipeline event sent over Server-Sent Events."""

    type: Literal[
        "pipeline:start",
        "pipeline:progress",
        "pipeline:complete",
        "pipeline:error",
        "audit:complete",
        "llm:chunk",
        "llm:progress",
    ]
    book_id: str
    chapter_no: int
    stage: str | None = None
    message: str | None = None
    detail: dict | None = None


class SSEManager:
    """Manage filtered SSE subscriptions and recent event replay."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[str]]] = defaultdict(list)
        self._recent: list[str] = []

    def _key(self, book_id: str, chapter_no: int) -> str:
        return f"{book_id}:{chapter_no}"

    async def publish(self, event: PipelineEvent) -> None:
        data = event.model_dump_json()
        self._recent.append(data)
        if len(self._recent) > 100:
            self._recent = self._recent[-100:]

        key = self._key(event.book_id, event.chapter_no)
        for queue in tuple(self._subscribers.get(key, ())):
            await queue.put(data)
        for queue in tuple(self._subscribers.get("_global", ())):
            await queue.put(data)

    async def subscribe(
        self,
        book_id: str | None = None,
        chapter_no: int | None = None,
    ) -> AsyncGenerator[str, None]:
        queue: asyncio.Queue[str] = asyncio.Queue()
        key = self._key(book_id, chapter_no) if book_id and chapter_no is not None else "_global"
        self._subscribers[key].append(queue)

        if key != "_global":
            for recent in self._recent:
                event = json.loads(recent)
                if event.get("book_id") == book_id and event.get("chapter_no") == chapter_no:
                    await queue.put(recent)

        try:
            while True:
                yield await queue.get()
        finally:
            subscribers = self._subscribers.get(key, [])
            if queue in subscribers:
                subscribers.remove(queue)


sse_manager = SSEManager()


def make_chunk_event(book_id: str, chapter_no: int, text: str) -> PipelineEvent:
    """Create an event carrying a streamed LLM text chunk."""
    return PipelineEvent(
        type="llm:chunk",
        book_id=book_id,
        chapter_no=chapter_no,
        stage="draft",
        detail={"text": text},
    )


def make_progress_event(book_id: str, chapter_no: int, completed: int, total: int) -> PipelineEvent:
    """Create an event reporting chunked generation progress."""
    return PipelineEvent(
        type="llm:progress",
        book_id=book_id,
        chapter_no=chapter_no,
        stage="draft",
        message=f"正在生成第 {completed}/{total} 段",
        detail={"completed": completed, "total": total},
    )
