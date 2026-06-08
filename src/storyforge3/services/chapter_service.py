from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from storyforge3.audit import thresholds as T
from storyforge3.audit.chinese_text import count_chinese_chars
from storyforge3.audit.llm_auditor import LLMAuditResult, LLMAuditor
from storyforge3.audit.revision_modes import RevisionMode, RevisionModeRecommender, get_mode_config
from storyforge3.audit.runner import AuditRunner
from storyforge3.config import StoryForge3Config
from storyforge3.export.formatter import PlatformFormatter
from storyforge3.llm.chunked_generator import ChunkedGenerator
from storyforge3.llm.factory import create_llm_service
from storyforge3.models import AuditResult, ChapterIntent, ChapterResult, Character, CharacterRole, WorldConfig
from storyforge3.prompts.registry import PromptRegistry, create_default_registry
from storyforge3.services.export_service import ExportService
from storyforge3.services.length_normalizer import LengthNormalizationResult, LengthNormalizer
from storyforge3.storage import BookStorage, StoragePaths
from storyforge3.style.imitation import StyleImitator, fingerprint_from_dict
from storyforge3.truth.extractor import TruthExtractor
from storyforge3.truth.retriever import TruthRetriever
from storyforge3.truth.store import TruthStore
from storyforge3.workflow import ChapterWorkflow


class ChapterService:
    def __init__(
        self,
        config: StoryForge3Config,
        *,
        llm: Any | None = None,
        storage: BookStorage | None = None,
        paths: StoragePaths | None = None,
        audit_runner: AuditRunner | None = None,
        truth_extractor: TruthExtractor | None = None,
        truth_store: TruthStore | None = None,
        prompt_registry: PromptRegistry | None = None,
    ) -> None:
        self.config = config
        self.llm = llm or create_llm_service(config)
        self.paths = paths or StoragePaths(Path(config.books_dir))
        self.storage = storage or BookStorage(self.paths.books_root)
        self.audit_runner = audit_runner or AuditRunner()
        self.prompt_registry = prompt_registry or create_default_registry()
        self.truth_store = truth_store or TruthStore(config.books_dir)
        self.truth_extractor = truth_extractor or TruthExtractor(self.llm, self.prompt_registry)
        self.formatter = PlatformFormatter()
        self.export_service = ExportService(self.storage, self.paths)
        self.truth_retriever = TruthRetriever(self.truth_store.database)
        self.revision_recommender = RevisionModeRecommender()

    async def plan(self, book_id: str, chapter_no: int) -> ChapterIntent:
        template = self.prompt_registry.get_latest("plan")
        prompt = self.prompt_registry.render_system_prompt(template, chapter_no=chapter_no)
        payload = {"book_id": book_id, "chapter_no": chapter_no, "context": self.storage.read_text(self.paths.context(book_id)) or ""}
        outline = await self.llm.generate_text("chapter_plan", prompt, payload, model=self.config.model_for_task("planner"))
        goal = self._extract_goal(outline)
        return ChapterIntent(chapter_no, goal, outline_node=outline)

    async def draft(self, book_id: str, chapter_no: int, intent: ChapterIntent | None = None) -> str:
        intent = intent or await self.plan(book_id, chapter_no)
        prompt = "你是中文网文作者。直接输出章节正文。"
        style_prompt = self._style_prompt_fragment(book_id)
        if style_prompt:
            prompt = f"{prompt}\n\n{style_prompt}"
        model = self.config.model_for_task("writer")
        book_context = self.storage.read_text(self.paths.context(book_id)) or ""
        truth_context = "\n".join((intent.goal, book_context))
        payload = {
            "book_id": book_id,
            "intent": intent.goal,
            "book_context": book_context,
            "world": self._world_summary(book_id),
            "characters": self._character_summaries(book_id),
            "relevant_truth": self.truth_retriever.retrieve_for_prompt(
                book_id,
                chapter_no,
                truth_context,
                max_chars=4000,
            ),
        }
        target_chars = self._load_target_chapter_chars(book_id)
        if _should_chunk_draft(target_chars):
            text = await ChunkedGenerator(self.llm).generate(
                "chapter_draft",
                prompt,
                intent.outline_node or intent.goal,
                {**payload, "target_chars": target_chars, "model": model},
            )
        else:
            text = await self.llm.generate_text("chapter_draft", prompt, payload, model=model)
        text = await self._normalize_draft_if_needed(book_id, text)
        self.storage.write_text(self.paths.chapter_file(book_id, chapter_no), text)
        return text

    async def audit(self, book_id: str, chapter_no: int) -> AuditResult:
        text = self.storage.read_text(self.paths.chapter_file(book_id, chapter_no))
        if text is None:
            raise FileNotFoundError(f"chapter not found: {book_id} {chapter_no}")
        return self.audit_runner.run_audit(chapter_no, text)

    async def run_llm_audit(self, book_id: str, chapter_no: int, text: str) -> LLMAuditResult:
        auditor = LLMAuditor(self.llm, self.prompt_registry, self.config)
        return await auditor.audit(
            chapter_text=text,
            characters=tuple(self._load_characters(book_id)),
            world=self._load_world(book_id),
            previous_truth=self.truth_store.load(book_id, chapter_no - 1) if chapter_no > 1 else None,
        )

    async def normalize_length(
        self,
        text: str,
        *,
        target_chars: int,
        soft_ratio: float = 0.15,
        hard_range: tuple[int, int] | None = None,
    ) -> LengthNormalizationResult:
        return await LengthNormalizer(self.llm, self.config).normalize(
            text,
            target_chars=target_chars,
            soft_ratio=soft_ratio,
            hard_range=hard_range,
        )

    async def revise(self, book_id: str, chapter_no: int, mode: str = "auto") -> ChapterResult:
        audit = await self.audit(book_id, chapter_no)
        text = self.storage.read_text(self.paths.chapter_file(book_id, chapter_no)) or ""
        failed = self.revision_recommender.failed_results(audit.rule_results)
        if mode == "auto":
            selected_mode = self.revision_recommender.recommend(
                failed,
                blocking_count=len(audit.blocking_issues),
                revision_round=0,
            )
            mode_source = "auto_recommended"
        else:
            selected_mode = RevisionMode(mode)
            mode_source = "manual"
        mode_config = get_mode_config(selected_mode)
        self._render_revision_prompt(selected_mode, mode_config.prompt_constraints, failed)
        return ChapterResult(
            book_id,
            chapter_no,
            self._workflow_status(book_id, chapter_no),
            f"第{chapter_no}章",
            text,
            audit=audit,
            error=f"revision_mode={selected_mode.value};mode_source={mode_source}",
        )

    async def approve(self, book_id: str, chapter_no: int) -> ChapterResult:
        result = await self.run_full_pipeline(book_id, chapter_no, human_confirm=lambda _: True)
        return result

    async def export(self, book_id: str, chapter_no: int, fmt: str = "tomato_txt") -> Path:
        return await self.export_service.export_chapter(book_id, chapter_no, fmt)

    async def get_status(self, book_id: str, chapter_no: int) -> ChapterResult | None:
        text = self.storage.read_text(self.paths.chapter_file(book_id, chapter_no))
        if text is None:
            return None
        return ChapterResult(book_id, chapter_no, self._workflow_status(book_id, chapter_no), f"第{chapter_no}章", text)

    async def run_full_pipeline(
        self,
        book_id: str,
        chapter_no: int,
        *,
        human_confirm: Callable[[ChapterResult], bool] | None = None,
    ) -> ChapterResult:
        workflow = ChapterWorkflow(self.config, client=self.llm, registry=self.prompt_registry)
        return await workflow.run(book_id, chapter_no, human_confirm=human_confirm)

    @staticmethod
    def _extract_goal(outline: str) -> str:
        goal = outline.replace("本章目标：", "").strip()
        return goal[:50] or "推进主线"

    def _workflow_status(self, book_id: str, chapter_no: int):
        from storyforge3.state.machine import ChapterStateMachine

        return ChapterStateMachine(self.paths.chapter_states(book_id)).current_status(book_id, chapter_no)

    def _render_revision_prompt(self, mode: RevisionMode, extra_constraints: tuple[str, ...], failed: list) -> str:
        template = self.prompt_registry.get_latest("revise")
        return self.prompt_registry.render_system_prompt(
            template,
            mode=mode.value,
            failed_rules="、".join(result.rule_id for result in failed) or "无",
            extra_constraints="\n".join(extra_constraints),
        )

    async def _normalize_draft_if_needed(self, book_id: str, text: str) -> str:
        target_chars = self._load_target_chapter_chars(book_id)
        if target_chars is None:
            return text
        hard_range = self._length_hard_range(target_chars)
        current_chars = count_chinese_chars(text)
        if hard_range[0] <= current_chars <= hard_range[1]:
            return text
        result = await self.normalize_length(
            text,
            target_chars=target_chars,
            soft_ratio=T.LENGTH_SOFT_RATIO,
            hard_range=hard_range,
        )
        return result.text

    def _load_target_chapter_chars(self, book_id: str) -> int | None:
        data = self.storage.read_json(self.paths.book_meta(book_id))
        if not data:
            return None
        value = data.get("chapter_word_count")
        if not isinstance(value, int) or value <= 0:
            return None
        return value

    def _style_prompt_fragment(self, book_id: str) -> str:
        data = self.storage.read_json(self.paths.book_meta(book_id)) or {}
        fingerprint = fingerprint_from_dict(data.get("style_fingerprint"))
        if fingerprint is None:
            return ""
        samples = data.get("style_reference_samples")
        reference_samples = [str(sample) for sample in samples] if isinstance(samples, list) else []
        return StyleImitator(self.llm).fingerprint_to_prompt(fingerprint, reference_samples)

    @staticmethod
    def _length_hard_range(target_chars: int) -> tuple[int, int]:
        return (int(target_chars * (1 - T.LENGTH_HARD_RATIO)), int(target_chars * (1 + T.LENGTH_HARD_RATIO)))

    def _load_world(self, book_id: str) -> WorldConfig | None:
        data = self.storage.read_json(self.paths.world_config(book_id))
        if not data:
            return None
        return WorldConfig(
            book_id,
            str(data.get("setting", "")),
            str(data.get("power_system", "")),
            str(data.get("core_conflict", "")),
            tuple(str(item) for item in data.get("rules", ())),
        )

    def _load_characters(self, book_id: str) -> list[Character]:
        data = self.storage.read_json(self.paths.characters(book_id)) or {"characters": []}
        characters: list[Character] = []
        for item in data.get("characters", []):
            characters.append(
                Character(
                    book_id,
                    str(item.get("name", "")),
                    CharacterRole(str(item.get("role", "minor"))),
                    str(item.get("profile", "")),
                    str(item.get("personality", "")),
                    tuple(str(value) for value in item.get("abilities", ())),
                    str(item.get("arc_direction", "")),
                )
            )
        return characters

    def _world_summary(self, book_id: str) -> dict[str, str]:
        world = self._load_world(book_id)
        if world is None:
            return {}
        return {
            "setting": world.setting,
            "power_system": world.power_system,
            "core_conflict": world.core_conflict,
        }

    def _character_summaries(self, book_id: str) -> list[dict[str, str]]:
        return [
            {
                "name": character.name,
                "role": character.role.value,
                "profile": character.profile,
                "personality": character.personality,
            }
            for character in self._load_characters(book_id)
            if character.name
        ]


def _should_chunk_draft(target_chars: int | None) -> bool:
    return target_chars is not None and target_chars > 800
