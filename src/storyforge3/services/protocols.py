"""Service interface definitions — the API boundary for all frontends.

Every method signature here IS the contract.  Frontend adapters (HTTP,
WebSocket, CLI) call through these protocols only; concrete implementations
are injected at composition time.

Design rules:
  - All service methods are async (future-proof for HTTP adapters).
  - Data in / out uses frozen dataclasses from storyforge3.models.
  - No filesystem paths leak through — services own storage.
  - No LLM details leak through — services own CCSwitch interaction.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

from storyforge3.models import (
    AuditResult,
    BookConfig,
    BookMeta,
    Character,
    ChapterIntent,
    ChapterResult,
    FanficCanon,
    FanficMode,
    Relationship,
    ShortStoryConfig,
    ShortStoryMeta,
    ShortStoryPlan,
    ShortStoryResult,
    TruthData,
    VolumeOutline,
    WorldConfig,
)
from storyforge3.audit.llm_auditor import LLMAuditResult
from storyforge3.services.length_normalizer import LengthNormalizationResult


# ── LLM routing ─────────────────────────────────────────────


class LLMServiceProtocol(Protocol):
    """CCSwitch proxy client with per-task model routing.

    Layer 1 (global): CCSwitch switches provider → all tools follow.
    Layer 2 (per-task): caller passes model= for task-specific routing.
    """

    async def generate_text(
        self,
        task_name: str,
        system_prompt: str,
        user_payload: dict,
        *,
        model: str | None = None,
        temperature: float | None = None,
    ) -> str: ...

    async def generate_json(
        self,
        task_name: str,
        system_prompt: str,
        user_payload: dict,
        response_schema: dict,
        *,
        model: str | None = None,
        temperature: float | None = None,
    ) -> dict: ...

    async def check_health(self) -> bool: ...


# ── Book management ─────────────────────────────────────────


class BookServiceProtocol(Protocol):
    """Book lifecycle: create, query, update status."""

    async def create(self, config: BookConfig) -> BookMeta: ...

    async def get(self, book_id: str) -> BookMeta | None: ...

    async def list_books(self) -> list[BookMeta]: ...

    async def update_status(self, book_id: str, status: str) -> BookMeta: ...


# ── World building ──────────────────────────────────────────


class WorldServiceProtocol(Protocol):
    """World construction and rule management."""

    async def build(self, book_id: str, genre: str, seed_brief: str) -> WorldConfig: ...

    async def get(self, book_id: str) -> WorldConfig | None: ...

    async def update(self, book_id: str, world: WorldConfig) -> WorldConfig: ...


# ── Character management ────────────────────────────────────


class CharacterServiceProtocol(Protocol):
    """Character creation, relationships, and arc management."""

    async def create(self, book_id: str, spec: str) -> Character: ...

    async def create_batch(self, book_id: str, specs: tuple[str, ...]) -> tuple[Character, ...]: ...

    async def list_characters(self, book_id: str) -> list[Character]: ...

    async def get_relationships(self, book_id: str) -> list[Relationship]: ...

    async def update(self, book_id: str, name: str, updates: dict) -> Character: ...


# ── Volume planning ─────────────────────────────────────────


class VolumeServiceProtocol(Protocol):
    """Volume structure and chapter allocation."""

    async def plan(
        self,
        book_id: str,
        volume_count: int,
        total_chapters: int,
    ) -> list[VolumeOutline]: ...

    async def get(self, book_id: str, volume_no: int) -> VolumeOutline | None: ...

    async def list_volumes(self, book_id: str) -> list[VolumeOutline]: ...

    async def update(
        self,
        book_id: str,
        volume_no: int,
        outline: VolumeOutline,
    ) -> VolumeOutline: ...


# ── Chapter lifecycle ───────────────────────────────────────


class ChapterServiceProtocol(Protocol):
    """Full chapter production pipeline.

    This is the primary service that frontend chapter pages interact with.
    It orchestrates: plan → compose → draft → settle → audit → revise →
    approve → export → state_update.
    """

    async def plan(self, book_id: str, chapter_no: int) -> ChapterIntent: ...

    async def re_plan(self, book_id: str, chapter_no: int) -> ChapterIntent: ...

    async def draft(
        self,
        book_id: str,
        chapter_no: int,
        intent: ChapterIntent | None = None,
        *,
        on_chunk_progress: Callable[[int, int], Awaitable[None]] | None = None,
    ) -> str: ...

    async def audit(self, book_id: str, chapter_no: int) -> AuditResult: ...

    async def re_audit(self, book_id: str, chapter_no: int) -> AuditResult: ...

    async def run_llm_audit(self, book_id: str, chapter_no: int, text: str) -> LLMAuditResult: ...

    async def normalize_length(
        self,
        text: str,
        *,
        target_chars: int,
        soft_ratio: float = 0.15,
        hard_range: tuple[int, int] | None = None,
    ) -> LengthNormalizationResult: ...

    async def revise(
        self,
        book_id: str,
        chapter_no: int,
        mode: str = "auto",
    ) -> ChapterResult: ...

    async def update_text(
        self,
        book_id: str,
        chapter_no: int,
        text: str,
        *,
        expected_hash: str | None = None,
    ) -> ChapterResult: ...

    async def approve(self, book_id: str, chapter_no: int) -> ChapterResult: ...

    async def export(
        self,
        book_id: str,
        chapter_no: int,
        fmt: str = "tomato_txt",
    ) -> Path: ...

    async def unexport(self, book_id: str, chapter_no: int) -> ChapterResult: ...

    async def get_status(self, book_id: str, chapter_no: int) -> ChapterResult | None: ...

    async def run_full_pipeline(
        self,
        book_id: str,
        chapter_no: int,
        *,
        human_confirm: object | None = None,
    ) -> ChapterResult: ...


# ── Quality audit ───────────────────────────────────────────


class AuditServiceProtocol(Protocol):
    """Quality gate: 36 mechanical rules + LLM auditor."""

    def run_mechanical(self, chapter_no: int, text: str) -> AuditResult: ...

    async def run_llm_audit(
        self,
        text: str,
        context: str,
        *,
        model: str | None = None,
        book_id: str | None = None,
    ) -> LLMAuditResult: ...


# ── Truth management ────────────────────────────────────────


class TruthServiceProtocol(Protocol):
    """Truth extraction, storage, and querying.

    Fail-closed: extraction failure → TruthExtractionError, never synthetic data.
    """

    async def extract(
        self,
        chapter_no: int,
        text: str,
        prev: TruthData | None = None,
    ) -> TruthData: ...

    def save(self, book_id: str, truth: TruthData) -> None: ...

    def load_latest(self, book_id: str) -> TruthData | None: ...

    def load_history(self, book_id: str) -> list[TruthData]: ...


# ── Platform export ─────────────────────────────────────────


class ExportServiceProtocol(Protocol):
    """Platform-specific chapter and book export."""

    async def export_chapter(
        self,
        book_id: str,
        chapter_no: int,
        fmt: str = "tomato_txt",
    ) -> Path: ...

    async def export_book(
        self,
        book_id: str,
        fmt: str = "tomato_txt",
        *,
        approved_only: bool = True,
    ) -> Path: ...


# ── Prompt management ───────────────────────────────────────


class PromptServiceProtocol(Protocol):
    """Versioned prompt template management."""

    def get(self, task_type: str, version: int | None = None) -> object: ...

    def render(self, task_type: str, **kwargs: object) -> str: ...

    def list_templates(self) -> list[dict]: ...


# ── Style management ────────────────────────────────────────


class StyleServiceProtocol(Protocol):
    """Style contract and compliance checking."""

    def get_contract(self, book_id: str) -> object: ...

    def check_compliance(self, text: str, contract: object) -> object: ...

    def save_contract(self, book_id: str, contract: object) -> None: ...


# ── Fanfiction canon ────────────────────────────────────────


class FanficServiceProtocol(Protocol):
    """Fanfiction canon import and management."""

    async def import_canon(
        self,
        book_id: str,
        source_text: str,
        source_name: str,
        mode: FanficMode,
    ) -> FanficCanon: ...

    async def refresh_canon(self, book_id: str, source_text: str) -> FanficCanon: ...

    def get_canon(self, book_id: str) -> FanficCanon | None: ...


# ── Short story pipeline ────────────────────────────────────


class ShortStoryServiceProtocol(Protocol):
    """Short story creation pipeline."""

    async def create(self, config: ShortStoryConfig) -> ShortStoryMeta: ...

    def list_stories(self) -> list[ShortStoryMeta]: ...

    async def plan(self, book_id: str) -> ShortStoryPlan: ...

    async def draft(self, book_id: str) -> str: ...

    async def audit(self, book_id: str) -> AuditResult: ...

    async def revise(self, book_id: str) -> ShortStoryResult: ...

    async def export(self, book_id: str, fmt: str = "tomato_txt") -> Path: ...

    async def run_full_pipeline(self, book_id: str) -> ShortStoryResult: ...

    def get_status(self, book_id: str) -> ShortStoryResult | None: ...
