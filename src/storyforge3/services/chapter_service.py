from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from storyforge3.audit import thresholds as T
from storyforge3.audit.chinese_text import count_chinese_chars
from storyforge3.audit.revision_diff import build_revision_diff
from storyforge3.audit.llm_auditor import LLMAuditResult, LLMAuditor
from storyforge3.audit.revision_modes import RevisionMode, RevisionModeRecommender, get_mode_config
from storyforge3.audit.runner import AuditRunner
from storyforge3.config import StoryForge3Config
from storyforge3.export.formatter import PlatformFormatter
from storyforge3.fanfic.dimensions import FANFIC_DIMENSIONS, get_fanfic_dimension_config
from storyforge3.fanfic.prompt_sections import build_character_voice_profiles, build_fanfic_canon_section, build_fanfic_mode_instructions
from storyforge3.llm.chunked_generator import ChunkedGenerator
from storyforge3.llm.factory import create_llm_service
from storyforge3.logging.pipeline_logger import PipelineLogger
from storyforge3.models import AuditResult, ChapterIntent, ChapterResult, ChapterStatus, Character, CharacterRole, FanficCanon, FanficMode, RuleCategory, RuleResult, RuleSeverity, WorldConfig
from storyforge3.prompts.registry import PromptRegistry, create_default_registry
from storyforge3.services.export_service import ExportService
from storyforge3.services.length_normalizer import LengthNormalizationResult, LengthNormalizer
from storyforge3.storage import BookStorage, StoragePaths
from storyforge3.state.machine import ChapterStateMachine, InvalidTransitionError
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
        pipeline_logger: PipelineLogger | None = None,
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
        self.pipeline_logger = pipeline_logger

    async def plan(self, book_id: str, chapter_no: int) -> ChapterIntent:
        template = self.prompt_registry.get_latest("plan")
        prompt = self.prompt_registry.render_system_prompt(template, chapter_no=chapter_no)
        payload = {"book_id": book_id, "chapter_no": chapter_no, "context": self.storage.read_text(self.paths.context(book_id)) or ""}
        outline = await self.llm.generate_text("chapter_plan", prompt, payload, model=self.config.model_for_task("planner"))
        goal = self._extract_goal(outline)
        intent = ChapterIntent(chapter_no, goal, outline_node=outline)
        self._save_plan(book_id, intent)
        self._advance_planned_state(book_id, chapter_no)
        self._bump_current_chapter(book_id, chapter_no)
        return intent

    async def get_plan(self, book_id: str, chapter_no: int) -> ChapterIntent | None:
        return self._load_plan(book_id, chapter_no)

    async def draft(
        self,
        book_id: str,
        chapter_no: int,
        intent: ChapterIntent | None = None,
        *,
        on_chunk_progress: Callable[[int, int], Awaitable[None]] | None = None,
        on_chunk: Callable[[str, int, int], Awaitable[None]] | None = None,
    ) -> str:
        intent = intent or self._load_plan(book_id, chapter_no) or await self.plan(book_id, chapter_no)
        template = self.prompt_registry.get_latest("compose")
        prompt = self.prompt_registry.render_system_prompt(template, chapter_no=chapter_no)
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
        payload.update(self._fanfic_draft_context(book_id))
        target_chars = self._load_target_chapter_chars(book_id)
        if _should_chunk_draft(target_chars):
            text = await ChunkedGenerator(self.llm, on_progress=on_chunk_progress, on_chunk=on_chunk).generate(
                "chapter_draft",
                prompt,
                intent.outline_node or intent.goal,
                {**payload, "target_chars": target_chars, "model": model},
            )
        else:
            text = await self.llm.generate_text("chapter_draft", prompt, payload, model=model)
        text = await self._normalize_draft_if_needed(book_id, text)
        self.storage.write_text(self.paths.chapter_file(book_id, chapter_no), text)
        # Advance chapter status PLANNED -> DRAFTED on a successful draft so the UI
        # (and downstream audit/revise gating) reflects that a draft artifact exists.
        # Idempotent: only advances from PLANNED, never regresses a later status.
        self._advance_draft_state(book_id, chapter_no)
        self._bump_current_chapter(book_id, chapter_no)
        return text

    async def audit(self, book_id: str, chapter_no: int) -> AuditResult:
        text = self.storage.read_text(self.paths.chapter_file(book_id, chapter_no))
        if text is None:
            raise FileNotFoundError(f"chapter not found: {book_id} {chapter_no}")
        audit = self.audit_runner.run_audit(chapter_no, text)
        self._save_audit_result(book_id, audit)
        # Segmented pipeline: auditing a draft/revised chapter advances to AUDITED
        # so the agent can drive stage-by-stage (draft -> audit -> revise -> approve).
        self._advance_audit_state(book_id, chapter_no)
        return audit

    async def run_llm_audit(self, book_id: str, chapter_no: int, text: str) -> LLMAuditResult:
        auditor = LLMAuditor(self.llm, self.prompt_registry, self.config)
        fanfic_context, fanfic_dimensions = self._fanfic_audit_context(book_id)
        return await auditor.audit(
            chapter_text=text,
            characters=tuple(self._load_characters(book_id)),
            world=self._load_world(book_id),
            previous_truth=self.truth_store.load(book_id, chapter_no - 1) if chapter_no > 1 else None,
            extra_context=fanfic_context,
            extra_dimensions=fanfic_dimensions,
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
        text = self.storage.read_text(self.paths.chapter_file(book_id, chapter_no))
        if text is None:
            raise FileNotFoundError(f"chapter not found: {book_id} {chapter_no}")
        audit = self.audit_runner.run_audit(chapter_no, text)
        current_status = self._workflow_status(book_id, chapter_no)
        title = f"第{chapter_no}章"
        if audit.passed:
            return ChapterResult(
                book_id,
                chapter_no,
                current_status,
                title,
                text,
                audit=audit,
                error="audit_passed_no_revision_needed",
            )
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
        self._write_before_snapshot(book_id, chapter_no, text)
        workflow = ChapterWorkflow(self.config, client=self.llm, registry=self.prompt_registry, logger=self.pipeline_logger)
        ctx = await workflow.step_import(book_id)
        revised_text = await workflow.step_revise(
            ctx,
            chapter_no,
            text,
            audit,
            revision_round=0,
            mode_override=selected_mode,
        )
        self.storage.write_text(self.paths.chapter_file(book_id, chapter_no), revised_text)
        self._advance_revision_state(book_id, chapter_no)
        revised_audit = self.audit_runner.run_audit(chapter_no, revised_text)
        return ChapterResult(
            book_id,
            chapter_no,
            ChapterStatus.REVISED,
            title,
            revised_text,
            audit=revised_audit,
            revision_diff=build_revision_diff(text, revised_text),
            error=f"revision_mode={selected_mode.value};mode_source={mode_source}",
        )

    async def approve(self, book_id: str, chapter_no: int) -> ChapterResult:
        # Segmented pipeline: approve = human-OK the current draft + extract truth,
        # then advance AUDITED -> APPROVED. Does NOT re-run plan/draft/audit (that's
        # the full pipeline's job via run()). This lets the agent resume a chapter
        # from its current draft instead of re-running everything.
        text = self.storage.read_text(self.paths.chapter_file(book_id, chapter_no))
        if text is None:
            raise FileNotFoundError(f"chapter not found: {book_id} {chapter_no}")
        previous_truth = self.truth_store.load(book_id, chapter_no - 1) if chapter_no > 1 else None
        truth = await self.truth_extractor.extract(chapter_no, text, previous_truth)
        self.truth_store.save(book_id, truth)
        self._advance_approve_state(book_id, chapter_no)
        return ChapterResult(
            book_id,
            chapter_no,
            ChapterStatus.TRUTH_COMMITTED,
            f"第{chapter_no}章",
            text,
            truth=truth,
            error="approved+truth_extracted",
        )

    async def export(self, book_id: str, chapter_no: int, fmt: str = "tomato_txt") -> Path:
        current = self._workflow_status(book_id, chapter_no)
        if current not in (ChapterStatus.TRUTH_COMMITTED, ChapterStatus.EXPORTED):
            raise ValueError("Truth 提取未完成，无法导出。请先批准并提交 truth。")
        path = await self.export_service.export_chapter(book_id, chapter_no, fmt)
        # Segmented pipeline: a successful export advances APPROVED -> EXPORTED.
        self._advance_export_state(book_id, chapter_no)
        return path

    async def get_status(self, book_id: str, chapter_no: int) -> ChapterResult | None:
        text = self.storage.read_text(self.paths.chapter_file(book_id, chapter_no))
        if text is not None:
            status = self._workflow_status(book_id, chapter_no)
            truth = None
            if status in (ChapterStatus.TRUTH_COMMITTED, ChapterStatus.EXPORTED):
                truth = self.truth_store.load(book_id, chapter_no)
            audit_result = self._status_audit_result(book_id, chapter_no, status, text)
            return ChapterResult(book_id, chapter_no, status, f"第{chapter_no}章", text, truth=truth, audit_result=audit_result)
        if self._load_plan(book_id, chapter_no) is not None:
            return ChapterResult(book_id, chapter_no, ChapterStatus.PLANNED, f"第{chapter_no}章", "")
        return None

    async def update_text(
        self,
        book_id: str,
        chapter_no: int,
        text: str,
        *,
        expected_hash: str | None = None,
    ) -> ChapterResult:
        current = await self.get_status(book_id, chapter_no)
        if current is None:
            raise FileNotFoundError(f"chapter not found: {book_id} {chapter_no}")
        if not current.text.strip():
            raise ValueError("空章节请先使用 draft 管线生成正文")
        if expected_hash and _content_fingerprint(current.text) != expected_hash:
            raise ValueError("章节内容已被修改，请刷新后重试")

        self._write_before_snapshot(book_id, chapter_no, current.text)
        self.storage.write_text(self.paths.chapter_file(book_id, chapter_no), text)
        from storyforge3.state.machine import ChapterStateMachine

        ChapterStateMachine(self.paths.chapter_states(book_id)).force_needs_review(book_id, chapter_no, reason="manual_edit")
        return ChapterResult(book_id, chapter_no, ChapterStatus.NEEDS_REVIEW, current.title, text)

    async def run_full_pipeline(
        self,
        book_id: str,
        chapter_no: int,
        *,
        human_confirm: Callable[[ChapterResult], bool] | None = None,
    ) -> ChapterResult:
        workflow = ChapterWorkflow(self.config, client=self.llm, registry=self.prompt_registry, logger=self.pipeline_logger)
        return await workflow.run(book_id, chapter_no, human_confirm=human_confirm)

    @staticmethod
    def _extract_goal(outline: str) -> str:
        lines = [line.strip() for line in outline.splitlines()]
        for index, line in enumerate(lines):
            if line.startswith("### 本章目标"):
                for candidate in lines[index + 1 :]:
                    if candidate and not candidate.startswith("### "):
                        return ChapterService._clean_goal_line(candidate)
                break
        for line in lines:
            if line.startswith("本章目标") or line.startswith("一句话"):
                return ChapterService._clean_goal_line(line)
        return ChapterService._clean_goal_line(outline)

    @staticmethod
    def _clean_goal_line(value: str) -> str:
        goal = value.strip()
        for prefix in ("本章目标：", "本章目标:", "一句话：", "一句话:"):
            if goal.startswith(prefix):
                goal = goal[len(prefix) :].strip()
        return goal[:50] or "推进主线"

    def _workflow_status(self, book_id: str, chapter_no: int):
        return ChapterStateMachine(self.paths.chapter_states(book_id)).current_status(book_id, chapter_no)

    def _advance_revision_state(self, book_id: str, chapter_no: int) -> None:
        machine = ChapterStateMachine(self.paths.chapter_states(book_id))
        while True:
            current = machine.current_status(book_id, chapter_no)
            if current == ChapterStatus.REVISED:
                return
            if current == ChapterStatus.NEEDS_REVISION:
                machine.advance(book_id, chapter_no, ChapterStatus.REVISED)
                return
            if current == ChapterStatus.AUDITED:
                machine.advance(book_id, chapter_no, ChapterStatus.NEEDS_REVISION)
                continue
            if current == ChapterStatus.DRAFTED:
                machine.advance(book_id, chapter_no, ChapterStatus.AUDITED)
                continue
            if current == ChapterStatus.PLANNED:
                machine.advance(book_id, chapter_no, ChapterStatus.DRAFTED)
                continue
            if current == ChapterStatus.EMPTY:
                machine.advance(book_id, chapter_no, ChapterStatus.PLANNED)
                continue
            raise ValueError(f"章节当前状态 {current.value} 不支持 revise")

    def _write_before_snapshot(self, book_id: str, chapter_no: int, text: str) -> None:
        self.storage.write_text(self.paths.chapter_file(book_id, chapter_no).with_suffix(".before.md"), text)

    def _save_plan(self, book_id: str, intent: ChapterIntent) -> None:
        self.storage.write_json(
            self.paths.plan_file(book_id, intent.chapter_no),
            {
                "chapter_no": intent.chapter_no,
                "goal": intent.goal,
                "outline_node": intent.outline_node,
                "arc_context": intent.arc_context,
                "must_keep": list(intent.must_keep),
                "must_avoid": list(intent.must_avoid),
                "style_emphasis": list(intent.style_emphasis),
            },
        )

    def _load_plan(self, book_id: str, chapter_no: int) -> ChapterIntent | None:
        data = self.storage.read_json(self.paths.plan_file(book_id, chapter_no))
        if not data:
            return None
        return ChapterIntent(
            chapter_no=int(data.get("chapter_no", chapter_no)),
            goal=str(data.get("goal", "")),
            outline_node=str(data.get("outline_node", "")),
            arc_context=str(data.get("arc_context", "")),
            must_keep=tuple(str(item) for item in data.get("must_keep", ())),
            must_avoid=tuple(str(item) for item in data.get("must_avoid", ())),
            style_emphasis=tuple(str(item) for item in data.get("style_emphasis", ())),
        )

    def _status_audit_result(self, book_id: str, chapter_no: int, status: ChapterStatus, text: str) -> AuditResult | None:
        if status not in (
            ChapterStatus.AUDITED,
            ChapterStatus.NEEDS_REVISION,
            ChapterStatus.REVISED,
            ChapterStatus.APPROVED,
            ChapterStatus.TRUTH_COMMITTED,
            ChapterStatus.EXPORTED,
        ):
            return None
        return self._load_audit_result(book_id, chapter_no) or self.audit_runner.run_audit(chapter_no, text)

    def _save_audit_result(self, book_id: str, audit: AuditResult) -> None:
        self.storage.write_json(self.paths.audit_result_file(book_id, audit.chapter_no), _audit_to_json(audit))

    def _load_audit_result(self, book_id: str, chapter_no: int) -> AuditResult | None:
        data = self.storage.read_json(self.paths.audit_result_file(book_id, chapter_no))
        if not data:
            return None
        return _audit_from_json(data, chapter_no)

    def _advance_planned_state(self, book_id: str, chapter_no: int) -> None:
        machine = ChapterStateMachine(self.paths.chapter_states(book_id))
        current = machine.current_status(book_id, chapter_no)
        if current != ChapterStatus.EMPTY:
            return
        try:
            machine.advance(book_id, chapter_no, ChapterStatus.PLANNED)
        except InvalidTransitionError:
            return

    def _advance_draft_state(self, book_id: str, chapter_no: int) -> None:
        machine = ChapterStateMachine(self.paths.chapter_states(book_id))
        current = machine.current_status(book_id, chapter_no)
        if current != ChapterStatus.PLANNED:
            return
        try:
            machine.advance(book_id, chapter_no, ChapterStatus.DRAFTED)
        except InvalidTransitionError:
            return

    def _advance_audit_state(self, book_id: str, chapter_no: int) -> None:
        # Segmented: auditing a fresh draft or a revised chapter lands at AUDITED.
        machine = ChapterStateMachine(self.paths.chapter_states(book_id))
        current = machine.current_status(book_id, chapter_no)
        if current not in (ChapterStatus.DRAFTED, ChapterStatus.REVISED):
            return
        try:
            machine.advance(book_id, chapter_no, ChapterStatus.AUDITED)
        except InvalidTransitionError:
            return

    def _advance_approve_state(self, book_id: str, chapter_no: int) -> None:
        # Segmented: approve in the current service performs human approval and
        # truth extraction together, so the durable product state lands at
        # TRUTH_COMMITTED after passing through APPROVED.
        machine = ChapterStateMachine(self.paths.chapter_states(book_id))
        current = machine.current_status(book_id, chapter_no)
        if current == ChapterStatus.TRUTH_COMMITTED:
            return
        try:
            if current == ChapterStatus.AUDITED:
                machine.advance(book_id, chapter_no, ChapterStatus.APPROVED)
                current = ChapterStatus.APPROVED
            if current == ChapterStatus.APPROVED:
                machine.advance(book_id, chapter_no, ChapterStatus.TRUTH_COMMITTED)
        except InvalidTransitionError:
            return

    def _advance_export_state(self, book_id: str, chapter_no: int) -> None:
        # Segmented: a successful export advances TRUTH_COMMITTED -> EXPORTED.
        machine = ChapterStateMachine(self.paths.chapter_states(book_id))
        current = machine.current_status(book_id, chapter_no)
        if current == ChapterStatus.EXPORTED:
            return
        if current != ChapterStatus.TRUTH_COMMITTED:
            return
        try:
            machine.advance(book_id, chapter_no, ChapterStatus.EXPORTED)
        except InvalidTransitionError:
            return

    def _bump_current_chapter(self, book_id: str, chapter_no: int) -> None:
        data = self.storage.read_json(self.paths.book_meta(book_id))
        if not data:
            return
        current = int(data.get("current_chapter", 0) or 0)
        if chapter_no <= current:
            return
        data["current_chapter"] = chapter_no
        self.storage.write_json(self.paths.book_meta(book_id), data)

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

    def _fanfic_draft_context(self, book_id: str) -> dict[str, str]:
        mode = self._get_fanfic_mode(book_id)
        if mode is None:
            return {}
        canon = self._load_fanfic_canon(book_id)
        if canon is None:
            return {}
        voice_profiles = build_character_voice_profiles(canon.full_document)
        return {
            "fanfic_canon": build_fanfic_canon_section(canon),
            "character_voice_profiles": voice_profiles,
            "fanfic_mode_instructions": build_fanfic_mode_instructions(mode),
        }

    def _fanfic_audit_context(self, book_id: str) -> tuple[str, tuple[str, ...]]:
        mode = self._get_fanfic_mode(book_id)
        if mode is None:
            return "", ()
        canon = self._load_fanfic_canon(book_id)
        if canon is None:
            return "", ()
        config = get_fanfic_dimension_config(mode)
        dimension_lines = []
        for dimension in FANFIC_DIMENSIONS:
            dimension_id = int(dimension["id"])
            severity = config["severity_overrides"][dimension_id].value
            note = config["notes"][dimension_id]
            dimension_lines.append(f"- {dimension_id} {dimension['name']} [{severity}]：{note}")
        context = "\n".join(
            [
                f"## 同人审计模式：{mode.value}",
                "",
                "### 同人审计维度",
                *dimension_lines,
                "",
                build_fanfic_canon_section(canon),
                "",
                build_character_voice_profiles(canon.full_document),
                "",
                build_fanfic_mode_instructions(mode),
            ]
        )
        return context, tuple(str(dimension["name"]) for dimension in FANFIC_DIMENSIONS)

    def _get_fanfic_mode(self, book_id: str) -> FanficMode | None:
        data = self.storage.read_json(self.paths.book_meta(book_id)) or {}
        value = str(data.get("fanfic_mode") or "").strip()
        if not value:
            return None
        try:
            return FanficMode(value)
        except ValueError:
            return None

    def _load_fanfic_canon(self, book_id: str) -> FanficCanon | None:
        data = self.storage.read_json(self.paths.book_dir(book_id) / "fanfic_canon.json")
        if not data:
            return None
        try:
            return FanficCanon(**{**data, "mode": FanficMode(str(data.get("mode", "")))})
        except ValueError:
            return None

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


def _content_fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def _enum_value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _audit_to_json(audit: AuditResult) -> dict[str, Any]:
    return {
        "chapter_no": audit.chapter_no,
        "passed": audit.passed,
        "blocking_issues": list(audit.blocking_issues),
        "warnings": list(audit.warnings),
        "info": list(audit.info),
        "rule_results": [
            {
                "rule_id": result.rule_id,
                "passed": result.passed,
                "severity": _enum_value(result.severity),
                "category": _enum_value(result.category),
                "message": result.message,
                "detail": dict(result.detail),
            }
            for result in audit.rule_results
        ],
    }


def _audit_from_json(data: dict[str, Any], chapter_no: int) -> AuditResult:
    return AuditResult(
        chapter_no=int(data.get("chapter_no", chapter_no)),
        passed=bool(data.get("passed", False)),
        blocking_issues=tuple(data.get("blocking_issues", ())),
        warnings=tuple(data.get("warnings", ())),
        info=tuple(data.get("info", ())),
        rule_results=tuple(_rule_result_from_json(item) for item in data.get("rule_results", ())),
    )


def _rule_result_from_json(data: dict[str, Any]) -> RuleResult:
    return RuleResult(
        rule_id=str(data.get("rule_id", "")),
        passed=bool(data.get("passed", False)),
        severity=_rule_severity(data.get("severity", RuleSeverity.INFO.value)),
        category=_rule_category(data.get("category", RuleCategory.META.value)),
        message=str(data.get("message", "")),
        detail=dict(data.get("detail", {})),
    )


def _rule_severity(value: Any) -> RuleSeverity:
    raw = str(value)
    try:
        return RuleSeverity(raw.lower())
    except ValueError:
        return RuleSeverity[raw.upper()]


def _rule_category(value: Any) -> RuleCategory:
    raw = str(value)
    try:
        return RuleCategory(raw.lower())
    except ValueError:
        return RuleCategory[raw.upper()]
