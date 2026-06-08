from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from storyforge3.audit import thresholds as T
from storyforge3.audit.chinese_text import count_chinese_chars
from storyforge3.audit.revision_patch import apply_patches, build_patch_targets, validate_patch_response
from storyforge3.audit.revision_modes import RevisionModeRecommender, get_mode_config
from storyforge3.audit.runner import AuditRunner
from storyforge3.config import StoryForge3Config
from storyforge3.export.formatter import PlatformFormatter
from storyforge3.llm.chunked_generator import ChunkedGenerator
from storyforge3.llm.factory import create_llm_service
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
    ) -> None:
        self.config = config
        self.client = client or create_llm_service(config)
        self.registry = registry or create_default_registry()
        self.audit_runner = AuditRunner()
        self.truth_store = TruthStore(config.books_dir)
        self.truth_retriever = TruthRetriever(self.truth_store.database)
        self.truth_extractor = TruthExtractor(self.client, self.registry)
        self.formatter = PlatformFormatter()
        self.state_machine = ChapterStateMachine(Path(config.books_dir) / "state.json")
        self.revision_recommender = RevisionModeRecommender()

    async def run(
        self,
        book_id: str,
        chapter_no: int,
        human_confirm: Callable[[ChapterResult], bool] | None = None,
    ) -> ChapterResult:
        title = f"第{chapter_no}章"
        text = ""
        audit: AuditResult | None = None
        llm_calls: list[LLMCallRecord] = []
        try:
            ctx = await self.step_import(book_id)
            self._advance(book_id, chapter_no, ChapterStatus.PLANNED)
            plan = await self.step_plan(ctx, chapter_no)
            self._append_last_call(llm_calls)

            self._advance(book_id, chapter_no, ChapterStatus.DRAFTED)
            text = await self.step_draft(plan, ctx, chapter_no)
            self._append_last_call(llm_calls)
            normalization = await self.step_normalize_draft(book_id, text)
            if normalization.action != "none":
                self._append_last_call(llm_calls)
            text = normalization.text

            audit = self.step_audit(chapter_no, text)
            self._advance(book_id, chapter_no, ChapterStatus.AUDITED)

            if not audit.passed:
                text, audit = await self._revise_until_passes(book_id, chapter_no, title, text, audit, ctx, llm_calls)
                if not audit.passed:
                    return self._needs_review(book_id, chapter_no, title, text, "revision_exhausted", audit, None, llm_calls)
            preview = ChapterResult(book_id, chapter_no, ChapterStatus.AUDITED, title, text, audit=audit, llm_calls=tuple(llm_calls))
            if human_confirm is None:
                return self._needs_review(book_id, chapter_no, title, text, "human_confirmation_required", audit, None, llm_calls)
            if not human_confirm(preview):
                return self._needs_review(book_id, chapter_no, title, text, "human_rejected", audit, None, llm_calls)

            truth = await self.truth_extractor.extract(chapter_no, text, ctx.previous_truth)
            self._append_last_call(llm_calls)
            self.truth_store.save(book_id, truth)

            self._advance(book_id, chapter_no, ChapterStatus.APPROVED)
            await self.step_export(chapter_no, title, text, book_id)
            self._advance(book_id, chapter_no, ChapterStatus.EXPORTED)
            return ChapterResult(book_id, chapter_no, ChapterStatus.EXPORTED, title, text, audit=audit, truth=truth, llm_calls=tuple(llm_calls))
        except TruthExtractionError as exc:
            return self._needs_review(book_id, chapter_no, title, text, f"truth_extraction_failed: {exc.reason}", audit, None, llm_calls)
        except Exception as exc:
            return self._needs_review(book_id, chapter_no, title, "", str(exc), None, None, llm_calls)

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
        truth_context = "\n".join((plan, ctx.context_text, previous_chapter_tail))
        payload = {
            "book_id": ctx.book_id,
            "chapter_no": chapter_no,
            "book_context": ctx.context_text,
            "previous_chapter_tail": previous_chapter_tail,
            "world": ctx.world,
            "characters": ctx.characters,
            "relevant_truth": self.truth_retriever.retrieve_for_prompt(
                ctx.book_id,
                chapter_no,
                truth_context,
                max_chars=4000,
            ),
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

    async def step_revise(self, ctx: BookContext, chapter_no: int, text: str, audit: AuditResult, revision_round: int) -> str:
        failed = self.revision_recommender.failed_results(audit.rule_results)
        mode = self.revision_recommender.recommend(
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
            self._advance(book_id, chapter_no, ChapterStatus.NEEDS_REVISION)
            text = await self.step_revise(ctx, chapter_no, text, audit, revision_round)
            self._append_last_call(llm_calls)
            self._advance(book_id, chapter_no, ChapterStatus.REVISED)
            audit = self.step_audit(chapter_no, text)
            self._advance(book_id, chapter_no, ChapterStatus.AUDITED)
            if audit.passed:
                return text, audit
        return text, audit

    async def step_export(self, chapter_no: int, title: str, text: str, book_id: str) -> Path:
        output_dir = Path(self.config.books_dir) / book_id / "exports"
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"chapter-{chapter_no:04d}.txt"
        path.write_text(self.formatter.format_chapter(title, chapter_no, text), encoding="utf-8")
        return path

    def _advance(self, book_id: str, chapter_no: int, status: ChapterStatus) -> None:
        try:
            self.state_machine.advance(book_id, chapter_no, status)
        except InvalidTransitionError:
            self.state_machine.force_needs_review(book_id, chapter_no, f"invalid_transition_to_{status.value}")
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
        self.state_machine.force_needs_review(book_id, chapter_no, error)
        return ChapterResult(book_id, chapter_no, ChapterStatus.NEEDS_REVIEW, title, text, audit=audit, truth=truth, llm_calls=tuple(llm_calls), error=error)

    def _append_last_call(self, records: list[LLMCallRecord]) -> None:
        call = getattr(self.client, "last_call", None)
        if isinstance(call, LLMCallRecord):
            records.append(call)

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
