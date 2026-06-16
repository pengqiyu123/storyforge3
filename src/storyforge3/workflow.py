from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter

from storyforge3.audit import thresholds as T
from storyforge3.audit.chinese_text import count_chinese_chars
from storyforge3.audit.revision_patch import apply_patches, build_patch_targets, validate_patch_response
from storyforge3.audit.revision_modes import RevisionMode, RevisionModeRecommender, get_mode_config
from storyforge3.audit.runner import AuditRunner
from storyforge3.config import StoryForge3Config
from storyforge3.context import ContextBlock, ContextPackage, ContextPriority
from storyforge3.export.formatter import PlatformFormatter
from storyforge3.llm.chunked_generator import ChunkedGenerator
from storyforge3.llm.factory import create_llm_service
from storyforge3.logging.pipeline_logger import PipelineLogger, PipelineRunRecord
from storyforge3.models import AuditResult, ChapterResult, ChapterStatus, LLMCallRecord, TruthData
from storyforge3.prompts.registry import PromptRegistry, create_default_registry
from storyforge3.services.length_normalizer import LengthNormalizationResult, LengthNormalizer
from storyforge3.state.machine import ChapterStateMachine, InvalidTransitionError
from storyforge3.style.imitation import StyleImitator, fingerprint_from_dict
from storyforge3.truth.extractor import TruthExtractionError, TruthExtractor
from storyforge3.truth.retriever import TruthRetriever
from storyforge3.truth.store import TruthStore

MAX_REVISION_ROUNDS = 2
DRAFT_CHUNK_THRESHOLD_CHARS = 800


@dataclass(frozen=True)
class BookContext:
    book_id: str
    root: Path
    context_text: str
    previous_chapters: tuple[str, ...]
    previous_truth: TruthData | None
    world: dict[str, str]
    characters: tuple[dict[str, str], ...]


class ChapterWorkflow:
    """Single-chapter production loop with fail-closed boundaries."""

    def __init__(
        self,
        config: StoryForge3Config,
        *,
        client: object | None = None,
        registry: PromptRegistry | None = None,
        logger: PipelineLogger | None = None,
    ) -> None:
        self.config = config
        self.client = client or create_llm_service(config)
        self.registry = registry or create_default_registry()
        self._logger = logger
        self._last_log_error: str | None = None
        self._last_context_sources: list[dict] = []
        self.audit_runner = AuditRunner()
        self.truth_store = TruthStore(config.books_dir)
        self.truth_retriever = TruthRetriever(self.truth_store.database)
        self.truth_extractor = TruthExtractor(self.client, self.registry)
        self.formatter = PlatformFormatter()
        self.revision_recommender = RevisionModeRecommender()

    async def run(
        self,
        book_id: str,
        chapter_no: int,
        human_confirm: Callable[[ChapterResult], bool] | None = None,
    ) -> ChapterResult:
        full_started_at, full_started = self._log_start()
        title = f"第{chapter_no}章"
        text = ""
        audit: AuditResult | None = None
        llm_calls: list[LLMCallRecord] = []
        try:
            ctx = await self.step_import(book_id)
            plan_started_at, plan_started = self._log_start()
            plan_before = self._current_status_value(book_id, chapter_no)
            self._advance(book_id, chapter_no, ChapterStatus.PLANNED)
            try:
                plan = await self.step_plan(ctx, chapter_no)
                self._persist_plan(book_id, chapter_no, plan)
                self._append_last_call(llm_calls)
                self._log_run(
                    book_id,
                    chapter_no,
                    "plan",
                    status="success",
                    started_at=plan_started_at,
                    started_monotonic=plan_started,
                    llm_calls=llm_calls,
                    status_before=plan_before,
                    status_after=ChapterStatus.PLANNED.value,
                )
            except Exception as exc:
                self._append_last_call(llm_calls)
                self._log_run(
                    book_id,
                    chapter_no,
                    "plan",
                    status="failure",
                    error=str(exc),
                    started_at=plan_started_at,
                    started_monotonic=plan_started,
                    llm_calls=llm_calls,
                    status_before=plan_before,
                    status_after=self._current_status_value(book_id, chapter_no),
                )
                raise

            draft_started_at, draft_started = self._log_start()
            draft_before = self._current_status_value(book_id, chapter_no)
            self._advance(book_id, chapter_no, ChapterStatus.DRAFTED)
            try:
                text = await self.step_draft(plan, ctx, chapter_no)
                self._persist_chapter_text(book_id, chapter_no, text)
                self._append_last_call(llm_calls)
                self._log_run(
                    book_id,
                    chapter_no,
                    "draft",
                    status="success",
                    started_at=draft_started_at,
                    started_monotonic=draft_started,
                    llm_calls=llm_calls,
                    context_sources=self._last_context_sources,
                    status_before=draft_before,
                    status_after=ChapterStatus.DRAFTED.value,
                )
            except Exception as exc:
                self._append_last_call(llm_calls)
                self._log_run(
                    book_id,
                    chapter_no,
                    "draft",
                    status="failure",
                    error=str(exc),
                    started_at=draft_started_at,
                    started_monotonic=draft_started,
                    llm_calls=llm_calls,
                    context_sources=self._last_context_sources,
                    status_before=draft_before,
                    status_after=self._current_status_value(book_id, chapter_no),
                )
                raise
            normalization = await self.step_normalize_draft(book_id, text)
            if normalization.action != "none":
                self._append_last_call(llm_calls)
            text = normalization.text

            audit_started_at, audit_started = self._log_start()
            audit_before = self._current_status_value(book_id, chapter_no)
            try:
                audit = self.step_audit(chapter_no, text)
            except Exception as exc:
                self._log_run(
                    book_id,
                    chapter_no,
                    "audit",
                    status="failure",
                    error=str(exc),
                    started_at=audit_started_at,
                    started_monotonic=audit_started,
                    llm_calls=llm_calls,
                    status_before=audit_before,
                    status_after=self._current_status_value(book_id, chapter_no),
                )
                raise
            self._advance(book_id, chapter_no, ChapterStatus.AUDITED)
            self._log_audit_run(book_id, chapter_no, audit, audit_started_at, audit_started, llm_calls, audit_before, ChapterStatus.AUDITED.value)

            if not audit.passed:
                text, audit = await self._revise_until_passes(book_id, chapter_no, title, text, audit, ctx, llm_calls)
                if not audit.passed:
                    result = self._needs_review(book_id, chapter_no, title, text, "revision_exhausted", audit, None, llm_calls)
                    self._log_full_pipeline(book_id, chapter_no, result, full_started_at, full_started)
                    return result
            preview = ChapterResult(book_id, chapter_no, ChapterStatus.AUDITED, title, text, audit=audit, llm_calls=tuple(llm_calls))
            if human_confirm is None:
                result = self._needs_review(book_id, chapter_no, title, text, "human_confirmation_required", audit, None, llm_calls)
                self._log_full_pipeline(book_id, chapter_no, result, full_started_at, full_started)
                return result
            if not human_confirm(preview):
                result = self._needs_review(book_id, chapter_no, title, text, "human_rejected", audit, None, llm_calls)
                self._log_full_pipeline(book_id, chapter_no, result, full_started_at, full_started)
                return result

            truth = await self.truth_extractor.extract(chapter_no, text, ctx.previous_truth)
            self._append_last_call(llm_calls)
            self.truth_store.save(book_id, truth)

            approve_started_at, approve_started = self._log_start()
            approve_before = self._current_status_value(book_id, chapter_no)
            self._advance(book_id, chapter_no, ChapterStatus.APPROVED)
            self._advance(book_id, chapter_no, ChapterStatus.TRUTH_COMMITTED)
            self._log_run(
                book_id,
                chapter_no,
                "approve",
                status="success",
                started_at=approve_started_at,
                started_monotonic=approve_started,
                llm_calls=llm_calls,
                status_before=approve_before,
                status_after=ChapterStatus.TRUTH_COMMITTED.value,
            )
            if self.config.snapshot_enabled:
                self._create_snapshot(book_id, chapter_no)
            export_started_at, export_started = self._log_start()
            export_before = self._current_status_value(book_id, chapter_no)
            try:
                self._ensure_truth_persisted(book_id, chapter_no)
                await self.step_export(chapter_no, title, text, book_id)
                self._log_run(
                    book_id,
                    chapter_no,
                    "export",
                    status="success",
                    started_at=export_started_at,
                    started_monotonic=export_started,
                    llm_calls=llm_calls,
                    status_before=export_before,
                    status_after=ChapterStatus.EXPORTED.value,
                )
            except Exception as exc:
                self._log_run(
                    book_id,
                    chapter_no,
                    "export",
                    status="failure",
                    error=str(exc),
                    started_at=export_started_at,
                    started_monotonic=export_started,
                    llm_calls=llm_calls,
                    status_before=export_before,
                    status_after=self._current_status_value(book_id, chapter_no),
                )
                raise
            self._advance(book_id, chapter_no, ChapterStatus.EXPORTED)
            result = ChapterResult(book_id, chapter_no, ChapterStatus.EXPORTED, title, text, audit=audit, truth=truth, llm_calls=tuple(llm_calls))
            self._log_full_pipeline(book_id, chapter_no, result, full_started_at, full_started)
            return result
        except TruthExtractionError as exc:
            result = self._needs_review(book_id, chapter_no, title, text, f"truth_extraction_failed: {exc.reason}", audit, None, llm_calls)
            self._log_full_pipeline(book_id, chapter_no, result, full_started_at, full_started)
            return result
        except Exception as exc:
            result = self._needs_review(book_id, chapter_no, title, "", str(exc), None, None, llm_calls)
            self._log_full_pipeline(book_id, chapter_no, result, full_started_at, full_started)
            return result

    async def step_import(self, book_id: str) -> BookContext:
        root = Path(self.config.books_dir) / book_id
        context_path = root / "context.md"
        context_text = context_path.read_text(encoding="utf-8") if context_path.exists() else ""
        chapters = tuple(path.read_text(encoding="utf-8") for path in sorted((root / "chapters").glob("*.md")))
        return BookContext(
            book_id,
            root,
            context_text,
            chapters,
            self.truth_store.load_latest(book_id),
            self._load_world_summary(root),
            tuple(self._load_character_summaries(root)),
        )

    async def step_plan(self, ctx: BookContext, chapter_no: int) -> str:
        template = self.registry.get_latest("plan")
        prompt = self.registry.render_system_prompt(template, chapter_no=chapter_no)
        payload = {
            "book_id": ctx.book_id,
            "chapter_no": chapter_no,
            "book_context": ctx.context_text,
            "previous_chapter_tail": ctx.previous_chapters[-1][-1200:] if ctx.previous_chapters else "",
            "task": "生成章节计划，保持与真实小说上下文连续。",
        }
        return await self.client.generate_text("plan", prompt, payload, prompt_version=f"{template.prompt_id}:v{template.version}")

    async def step_draft(self, plan: str, ctx: BookContext, chapter_no: int) -> str:
        template = self.registry.get_latest("compose")
        prompt = self.registry.render_system_prompt(template, chapter_no=chapter_no)
        style_prompt = self._style_prompt_fragment(ctx.book_id)
        if style_prompt:
            prompt = f"{prompt}\n\n{style_prompt}"
        prompt_version = f"{template.prompt_id}:v{template.version}"
        previous_chapter_tail = ctx.previous_chapters[-1][-1800:] if ctx.previous_chapters else ""
        truth_text = self.truth_retriever.retrieve_for_prompt(
            ctx.book_id,
            chapter_no,
            "\n".join((plan, ctx.context_text, previous_chapter_tail)),
            max_chars=4000,
        )
        context_package = self._draft_context_package(plan, ctx, previous_chapter_tail, truth_text)
        context_package.trim_to_budget()
        self._last_context_sources = context_package.sources_summary()
        payload = {
            "book_id": ctx.book_id,
            "chapter_no": chapter_no,
            "book_context": ctx.context_text,
            "previous_chapter_tail": previous_chapter_tail,
            "world": ctx.world,
            "characters": ctx.characters,
            "relevant_truth": truth_text,
            "context_sources": context_package.sources_summary(),
            "context_prompt": context_package.to_prompt_text(),
            "plan": plan,
            "task": "根据计划直接输出下一章正文。",
        }
        target_chars = self._load_target_chapter_chars(ctx.book_id)
        if _should_chunk_draft(target_chars):
            return await ChunkedGenerator(self.client).generate(
                "draft",
                prompt,
                plan,
                {
                    **payload,
                    "target_chars": target_chars,
                    "model": self.config.model_for_task("writer"),
                    "prompt_version": prompt_version,
                },
            )
        return await self.client.generate_text("draft", prompt, payload, prompt_version=prompt_version)

    def _draft_context_package(self, plan: str, ctx: BookContext, previous_chapter_tail: str, truth_text: str) -> ContextPackage:
        package = ContextPackage(task="draft", budget_chars=12000)
        package.add(ContextBlock("chapter_goal", ContextPriority.CRITICAL, plan, {"book_id": ctx.book_id}))
        if previous_chapter_tail:
            package.add(ContextBlock("previous_chapter_tail", ContextPriority.CRITICAL, previous_chapter_tail, {"chars_from_tail": 1800}))
        if ctx.context_text:
            package.add(ContextBlock("book_context", ContextPriority.MEDIUM, ctx.context_text, {"book_id": ctx.book_id}))
        if ctx.world:
            world_text = "\n".join(f"{key}: {value}" for key, value in ctx.world.items() if value)
            if world_text:
                package.add(ContextBlock("world_rules", ContextPriority.HIGH, world_text, {"fields": tuple(ctx.world.keys())}))
        if ctx.characters:
            characters_text = "\n".join(
                f"{character['name']}({character['role']}): {character['profile']}"
                for character in ctx.characters
                if character.get("name")
            )
            if characters_text:
                package.add(ContextBlock("character_profiles", ContextPriority.HIGH, characters_text, {"count": len(ctx.characters)}))
        if truth_text:
            package.add(ContextBlock("truth_retrieval", ContextPriority.HIGH, truth_text, {"max_chars": 4000}))
        return package

    async def step_revise(
        self,
        ctx: BookContext,
        chapter_no: int,
        text: str,
        audit: AuditResult,
        revision_round: int,
        *,
        mode_override: RevisionMode | str | None = None,
    ) -> str:
        failed = self.revision_recommender.failed_results(audit.rule_results)
        mode = RevisionMode(mode_override) if mode_override is not None else self.revision_recommender.recommend(
            failed,
            blocking_count=len(audit.blocking_issues),
            revision_round=revision_round,
        )
        mode_config = get_mode_config(mode)
        if mode.value != "rework":
            return await self._step_patch_revise(ctx, chapter_no, text, audit, failed, mode.value, revision_round)
        template = self.registry.get_latest("revise")
        prompt = self.registry.render_system_prompt(
            template,
            mode=mode.value,
            failed_rules="、".join(result.rule_id for result in failed) or "无",
            extra_constraints="\n".join(mode_config.prompt_constraints),
        )
        payload = {
            "book_id": ctx.book_id,
            "chapter_no": chapter_no,
            "mode": mode.value,
            "revision_round": revision_round + 1,
            "failed_rules": tuple(result.rule_id for result in failed),
            "blocking_issues": audit.blocking_issues,
            "world": ctx.world,
            "characters": ctx.characters,
            "relevant_truth": self.truth_retriever.retrieve_for_prompt(
                ctx.book_id,
                chapter_no,
                " ".join(result.rule_id for result in failed),
                max_chars=4000,
            ),
            "previous_chapter_tail": ctx.previous_chapters[-1][-1200:] if ctx.previous_chapters else "",
            "chapter_text": text,
            "instruction": "修复 blocking audit 问题后，只输出完整章节正文。",
        }
        return await self.client.generate_text(
            "revise",
            prompt,
            payload,
            model=self.config.model_for_task("writer"),
            prompt_version=f"{template.prompt_id}:v{template.version}",
            **mode_config.generation_config_overrides,
        )

    async def _step_patch_revise(
        self,
        ctx: BookContext,
        chapter_no: int,
        text: str,
        audit: AuditResult,
        failed: list,
        mode: str,
        revision_round: int,
    ) -> str:
        patch_targets = build_patch_targets(text, failed)
        if not patch_targets:
            raise RuntimeError("patch_revise_failed: no patch targets")
        payload = {
            "book_id": ctx.book_id,
            "chapter_no": chapter_no,
            "mode": mode,
            "revision_round": revision_round + 1,
            "failed_rules": tuple(result.rule_id for result in failed),
            "blocking_issues": audit.blocking_issues,
            "world": ctx.world,
            "characters": ctx.characters,
            "relevant_truth": self.truth_retriever.retrieve_for_prompt(
                ctx.book_id,
                chapter_no,
                " ".join(result.rule_id for result in failed),
                max_chars=1200,
            ),
            "patch_targets": tuple(target.__dict__ for target in patch_targets),
            "instruction": (
                "只输出 JSON object。生成 find/replace 局部补丁；find 必须逐字来自 patch_targets 的 window_text，"
                "replace 只包含小说正文。不要输出完整章节。"
            ),
        }
        data = await self.client.generate_json(
            "revise",
            _patch_revision_prompt(),
            payload,
            _patch_revision_schema(),
            model=self.config.model_for_task("writer"),
            timeout=self.config.llm_draft_timeout_seconds,
            temperature=0.2,
            max_output_tokens=1200,
            prompt_version="patch-revise-v1",
        )
        patches = validate_patch_response(data)
        result = apply_patches(text, patches)
        if result.applied_count < 1:
            failure_rules = ",".join(failure.rule_id or "unknown" for failure in result.failures)
            raise RuntimeError(f"patch_revise_failed: no patches applied; failed_rules={failure_rules}")
        return result.text

    async def step_normalize_draft(self, book_id: str, text: str) -> LengthNormalizationResult:
        target_chars = self._load_target_chapter_chars(book_id)
        current_chars = count_chinese_chars(text)
        if target_chars is None:
            return LengthNormalizationResult(text, "none", current_chars, current_chars)
        hard_range = self._length_hard_range(target_chars)
        if hard_range[0] <= current_chars <= hard_range[1]:
            return LengthNormalizationResult(text, "none", current_chars, current_chars)
        return await LengthNormalizer(self.client, self.config).normalize(
            text,
            target_chars=target_chars,
            soft_ratio=T.LENGTH_SOFT_RATIO,
            hard_range=hard_range,
        )

    def step_audit(self, chapter_no: int, text: str) -> AuditResult:
        return self.audit_runner.run_audit(chapter_no, text)

    async def _revise_until_passes(
        self,
        book_id: str,
        chapter_no: int,
        title: str,
        text: str,
        audit: AuditResult,
        ctx: BookContext,
        llm_calls: list[LLMCallRecord],
    ) -> tuple[str, AuditResult]:
        for revision_round in range(MAX_REVISION_ROUNDS):
            revise_started_at, revise_started = self._log_start()
            revise_before = self._current_status_value(book_id, chapter_no)
            self._advance(book_id, chapter_no, ChapterStatus.NEEDS_REVISION)
            try:
                text = await self.step_revise(ctx, chapter_no, text, audit, revision_round)
                self._persist_chapter_text(book_id, chapter_no, text)
                self._append_last_call(llm_calls)
            except Exception as exc:
                self._append_last_call(llm_calls)
                self._log_run(
                    book_id,
                    chapter_no,
                    "revise",
                    status="failure",
                    error=str(exc),
                    started_at=revise_started_at,
                    started_monotonic=revise_started,
                    llm_calls=llm_calls,
                    status_before=revise_before,
                    status_after=self._current_status_value(book_id, chapter_no),
                )
                raise
            self._advance(book_id, chapter_no, ChapterStatus.REVISED)
            self._log_run(
                book_id,
                chapter_no,
                "revise",
                status="success",
                started_at=revise_started_at,
                started_monotonic=revise_started,
                llm_calls=llm_calls,
                status_before=revise_before,
                status_after=ChapterStatus.REVISED.value,
            )
            audit_started_at, audit_started = self._log_start()
            audit_before = self._current_status_value(book_id, chapter_no)
            audit = self.step_audit(chapter_no, text)
            self._advance(book_id, chapter_no, ChapterStatus.AUDITED)
            self._log_audit_run(book_id, chapter_no, audit, audit_started_at, audit_started, llm_calls, audit_before, ChapterStatus.AUDITED.value)
            if audit.passed:
                return text, audit
        return text, audit

    async def step_export(self, chapter_no: int, title: str, text: str, book_id: str) -> Path:
        output_dir = Path(self.config.books_dir) / book_id / "exports"
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"chapter-{chapter_no:04d}.txt"
        path.write_text(self.formatter.format_chapter(title, chapter_no, text), encoding="utf-8")
        return path

    def _ensure_truth_persisted(self, book_id: str, chapter_no: int) -> None:
        if self.truth_store.load(book_id, chapter_no) is None:
            raise TruthExtractionError(chapter_no, "Truth 提取未完成，无法导出。请重新运行 truth_extract 步骤。")

    def _persist_plan(self, book_id: str, chapter_no: int, outline: str) -> None:
        path = Path(self.config.books_dir) / book_id / "plans" / f"{chapter_no:04d}.json"
        data = {
            "chapter_no": chapter_no,
            "goal": self._extract_goal(outline),
            "outline_node": outline,
            "arc_context": "",
            "must_keep": [],
            "must_avoid": [],
            "style_emphasis": [],
        }
        self._atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2))

    def _persist_chapter_text(self, book_id: str, chapter_no: int, text: str) -> None:
        path = Path(self.config.books_dir) / book_id / "chapters" / f"{chapter_no:04d}.md"
        self._atomic_write_text(path, text)

    @staticmethod
    def _extract_goal(outline: str) -> str:
        lines = [line.strip() for line in outline.splitlines()]
        for index, line in enumerate(lines):
            if line.startswith("### 本章目标"):
                for candidate in lines[index + 1 :]:
                    if candidate and not candidate.startswith("### "):
                        return ChapterWorkflow._clean_goal_line(candidate)
                break
        for line in lines:
            if line.startswith("本章目标") or line.startswith("一句话"):
                return ChapterWorkflow._clean_goal_line(line)
        return ChapterWorkflow._clean_goal_line(outline)

    @staticmethod
    def _clean_goal_line(value: str) -> str:
        goal = value.strip()
        for prefix in ("本章目标：", "本章目标:", "一句话：", "一句话:"):
            if goal.startswith(prefix):
                goal = goal[len(prefix) :].strip()
        return goal[:50] or "推进主线"

    def _state_machine(self, book_id: str) -> ChapterStateMachine:
        return ChapterStateMachine(Path(self.config.books_dir) / book_id / "state" / "chapter_states.json")

    def _advance(self, book_id: str, chapter_no: int, status: ChapterStatus) -> None:
        machine = self._state_machine(book_id)
        try:
            machine.advance(book_id, chapter_no, status)
        except InvalidTransitionError:
            machine.force_needs_review(book_id, chapter_no, f"invalid_transition_to_{status.value}")
            raise

    def _needs_review(
        self,
        book_id: str,
        chapter_no: int,
        title: str,
        text: str,
        error: str,
        audit: AuditResult | None,
        truth: TruthData | None,
        llm_calls: list[LLMCallRecord],
    ) -> ChapterResult:
        self._state_machine(book_id).force_needs_review(book_id, chapter_no, error)
        self._persist_diagnostics(book_id, chapter_no, text, audit, error)
        return ChapterResult(book_id, chapter_no, ChapterStatus.NEEDS_REVIEW, title, text, audit=audit, truth=truth, llm_calls=tuple(llm_calls), error=error)

    def _persist_diagnostics(
        self,
        book_id: str,
        chapter_no: int,
        text: str,
        audit: AuditResult | None,
        error: str,
    ) -> None:
        """Write failure artifacts for post-mortem analysis."""
        diag_dir = Path(self.config.books_dir) / book_id / "diagnostics"
        diag_dir.mkdir(parents=True, exist_ok=True)
        prefix = diag_dir / f"chapter_{chapter_no}"

        if text:
            self._atomic_write_text(prefix.with_name(f"{prefix.name}_last_draft.md"), text)
        if audit is not None:
            self._atomic_write_text(
                prefix.with_name(f"{prefix.name}_audit.json"),
                json.dumps(asdict(audit), ensure_ascii=False, indent=2, default=str),
            )
        self._atomic_write_text(prefix.with_name(f"{prefix.name}_error.txt"), error)

    @staticmethod
    def _atomic_write_text(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(path)
        except BaseException:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def _append_last_call(self, records: list[LLMCallRecord]) -> None:
        call = getattr(self.client, "last_call", None)
        if isinstance(call, LLMCallRecord):
            records.append(call)

    @staticmethod
    def _log_start() -> tuple[str, float]:
        return PipelineLogger.now_iso(), perf_counter()

    def _current_status_value(self, book_id: str, chapter_no: int) -> str:
        return self._state_machine(book_id).current_status(book_id, chapter_no).value

    def _log_run(
        self,
        book_id: str,
        chapter_no: int,
        task: str,
        *,
        status: str,
        error: str | None = None,
        started_at: str | None = None,
        started_monotonic: float | None = None,
        llm_calls: list[LLMCallRecord] | tuple[LLMCallRecord, ...] | None = None,
        context_sources: list[dict] | None = None,
        status_before: str | None = None,
        status_after: str | None = None,
        audit_passed: bool | None = None,
        audit_blocking: int | None = None,
        audit_warnings: int | None = None,
    ) -> None:
        if self._logger is None:
            return
        finished_at = PipelineLogger.now_iso()
        duration_ms = (perf_counter() - started_monotonic) * 1000 if started_monotonic is not None else None
        record = PipelineRunRecord(
            book_id=book_id,
            chapter_no=chapter_no,
            task=task,
            timestamp=finished_at,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            status=status,
            error=error,
            llm_calls=[asdict(call) for call in llm_calls or ()],
            context_sources=context_sources or [],
            status_before=status_before,
            status_after=status_after,
            audit_passed=audit_passed,
            audit_blocking=audit_blocking,
            audit_warnings=audit_warnings,
        )
        try:
            self._logger.append(record)
        except Exception as exc:
            self._last_log_error = str(exc)

    def _log_audit_run(
        self,
        book_id: str,
        chapter_no: int,
        audit: AuditResult,
        started_at: str,
        started_monotonic: float,
        llm_calls: list[LLMCallRecord],
        status_before: str | None,
        status_after: str | None,
    ) -> None:
        self._log_run(
            book_id,
            chapter_no,
            "audit",
            status="success",
            started_at=started_at,
            started_monotonic=started_monotonic,
            llm_calls=llm_calls,
            status_before=status_before,
            status_after=status_after,
            audit_passed=audit.passed,
            audit_blocking=len(audit.blocking_issues),
            audit_warnings=len(audit.warnings),
        )

    def _log_full_pipeline(
        self,
        book_id: str,
        chapter_no: int,
        result: ChapterResult,
        started_at: str,
        started_monotonic: float,
    ) -> None:
        self._log_run(
            book_id,
            chapter_no,
            "full_pipeline",
            status="success" if result.status == ChapterStatus.EXPORTED else "failure",
            error=result.error,
            started_at=started_at,
            started_monotonic=started_monotonic,
            llm_calls=result.llm_calls,
            status_after=result.status.value,
        )

    def _create_snapshot(self, book_id: str, chapter_no: int) -> None:
        """导出前创建快照；失败不阻塞主流程。"""
        try:
            from storyforge3.snapshot import SnapshotManager

            SnapshotManager(self.config.books_dir, max_count=self.config.snapshot_max_count).create_snapshot(book_id, chapter_no)
        except Exception as exc:
            self._last_snapshot_error = str(exc)

    def _load_target_chapter_chars(self, book_id: str) -> int | None:
        path = Path(self.config.books_dir) / book_id / "book.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        value = data.get("chapter_word_count")
        if not isinstance(value, int) or value <= 0:
            return None
        return value

    def _style_prompt_fragment(self, book_id: str) -> str:
        path = Path(self.config.books_dir) / book_id / "book.json"
        if not path.exists():
            return ""
        data = json.loads(path.read_text(encoding="utf-8"))
        fingerprint = fingerprint_from_dict(data.get("style_fingerprint"))
        if fingerprint is None:
            return ""
        samples = data.get("style_reference_samples")
        reference_samples = [str(sample) for sample in samples] if isinstance(samples, list) else []
        return StyleImitator(self.client).fingerprint_to_prompt(fingerprint, reference_samples)

    @staticmethod
    def _length_hard_range(target_chars: int) -> tuple[int, int]:
        return (int(target_chars * (1 - T.LENGTH_HARD_RATIO)), int(target_chars * (1 + T.LENGTH_HARD_RATIO)))

    @staticmethod
    def _load_world_summary(root: Path) -> dict[str, str]:
        path = root / "world.json"
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return {
            "setting": str(data.get("setting", "")),
            "power_system": str(data.get("power_system", "")),
            "core_conflict": str(data.get("core_conflict", "")),
        }

    @staticmethod
    def _load_character_summaries(root: Path) -> list[dict[str, str]]:
        path = root / "characters.json"
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        summaries: list[dict[str, str]] = []
        for item in data.get("characters", []):
            summaries.append(
                {
                    "name": str(item.get("name", "")),
                    "role": str(item.get("role", "")),
                    "profile": str(item.get("profile", "")),
                    "personality": str(item.get("personality", "")),
                }
            )
        return [summary for summary in summaries if summary["name"]]


def _should_chunk_draft(target_chars: int | None) -> bool:
    return target_chars is not None and target_chars > DRAFT_CHUNK_THRESHOLD_CHARS


def _patch_revision_prompt() -> str:
    return (
        "你是中文网文局部修订器。只输出 JSON object。"
        "根据 patch_targets 生成 find/replace 补丁。"
        "find 必须逐字来自对应 window_text，replace 只包含替换后的小说正文。"
        "禁止输出完整章节，禁止解释。"
    )


def _patch_revision_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "patches": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "find": {"type": "string"},
                        "replace": {"type": "string"},
                        "rule_id": {"type": "string"},
                    },
                    "required": ["find", "replace"],
                },
            }
        },
        "required": ["patches"],
    }
