from __future__ import annotations

import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from storyforge3.audit.chinese_text import count_chinese_chars
from storyforge3.audit.llm_auditor import LLMAuditResult, LLMAuditor
from storyforge3.audit.revision_patch import apply_patches, build_patch_targets, validate_patch_response
from storyforge3.audit.runner import AuditRunner
from storyforge3.config import StoryForge3Config
from storyforge3.export.epub_format import write_epub_book
from storyforge3.export.formatter import PlatformFormatter
from storyforge3.export.qidian import format_qidian_chapter, with_utf8_bom
from storyforge3.llm.chunked_generator import ChunkedGenerator
from storyforge3.llm.factory import create_llm_service
from storyforge3.models import (
    AuditResult,
    RuleCategory,
    RuleResult,
    RuleSeverity,
    ShortStoryConfig,
    ShortStoryMeta,
    ShortStoryPlan,
    ShortStoryResult,
    ShortStoryStatus,
)
from storyforge3.prompts.registry import PromptRegistry, create_default_registry
from storyforge3.storage import BookStorage, StoragePaths


SHORT_STORY_CHUNK_THRESHOLD_CHARS = 8000
SUPPORTED_SHORT_EXPORT_FORMATS = {"tomato_txt", "tomato", "txt", "md", "epub", "qidian_txt"}


class ShortStoryService:
    """Short story pipeline: plan -> draft -> audit -> revise -> export."""

    def __init__(
        self,
        config: StoryForge3Config,
        *,
        llm: Any | None = None,
        storage: BookStorage | None = None,
        paths: StoragePaths | None = None,
        audit_runner: AuditRunner | None = None,
        prompt_registry: PromptRegistry | None = None,
    ) -> None:
        self.config = config
        self.llm = llm or create_llm_service(config)
        self.paths = paths or StoragePaths(Path(config.books_dir))
        self.storage = storage or BookStorage(self.paths.books_root)
        self.audit_runner = audit_runner or AuditRunner()
        self.prompt_registry = prompt_registry or create_default_registry()
        self.formatter = PlatformFormatter()

    async def create(self, config: ShortStoryConfig) -> ShortStoryMeta:
        now = _now()
        meta = ShortStoryMeta(
            book_id=_make_short_story_id(config.title),
            title=config.title,
            genre=config.genre,
            status=ShortStoryStatus.EMPTY,
            target_chars=config.target_chars,
            premise=config.premise,
            style=config.style,
            created_at=now,
            updated_at=now,
        )
        self.storage.ensure_dir(self.paths.book_dir(meta.book_id) / "exports")
        self._save_meta(meta)
        return meta

    async def plan(self, book_id: str) -> ShortStoryPlan:
        meta = self._load_meta_or_raise(book_id)
        template = self.prompt_registry.get_latest("short_plan")
        prompt = self.prompt_registry.render_system_prompt(template, target_chars=meta.target_chars)
        payload = {
            "book_id": book_id,
            "title": meta.title,
            "genre": meta.genre,
            "target_chars": meta.target_chars,
            "premise": meta.premise,
            "style": meta.style,
            "task": "生成短篇小说规划，包含开篇、高潮、结尾和关键场景。",
        }
        outline = await self.llm.generate_text(
            "short_plan",
            prompt,
            payload,
            model=self.config.model_for_task("planner"),
            prompt_version=f"{template.prompt_id}:v{template.version}",
        )
        plan = _parse_plan(book_id, outline, fallback_premise=meta.premise)
        self.storage.write_json(self._plan_path(book_id), _dump_plan(plan))
        self._save_meta(self._with_meta_updates(meta, status=ShortStoryStatus.PLANNED))
        return plan

    async def draft(self, book_id: str) -> str:
        meta = self._load_meta_or_raise(book_id)
        plan = self._load_plan(book_id) or await self.plan(book_id)
        template = self.prompt_registry.get_latest("short_draft")
        prompt = self.prompt_registry.render_system_prompt(template, target_chars=meta.target_chars)
        prompt_version = f"{template.prompt_id}:v{template.version}"
        payload = {
            "book_id": book_id,
            "title": meta.title,
            "genre": meta.genre,
            "target_chars": meta.target_chars,
            "premise": plan.premise,
            "opening": plan.opening,
            "climax": plan.climax,
            "ending": plan.ending,
            "characters": plan.characters,
            "key_scenes": list(plan.key_scenes),
            "must_keep": list(plan.must_keep),
            "must_avoid": list(plan.must_avoid),
            "style": meta.style,
            "task": "根据短篇规划直接输出完整短篇正文。",
        }
        outline = self._plan_to_text(plan)
        if meta.target_chars > SHORT_STORY_CHUNK_THRESHOLD_CHARS:
            text = await ChunkedGenerator(self.llm).generate(
                "short_draft",
                prompt,
                outline,
                {
                    **payload,
                    "target_chars": meta.target_chars,
                    "model": self.config.model_for_task("writer"),
                    "prompt_version": prompt_version,
                },
            )
        else:
            text = await self.llm.generate_text(
                "short_draft",
                prompt,
                payload,
                model=self.config.model_for_task("writer"),
                prompt_version=prompt_version,
            )
        self._save_text(book_id, text)
        self._save_meta(self._with_meta_updates(meta, status=ShortStoryStatus.DRAFTED, actual_chars=count_chinese_chars(text)))
        return text

    async def audit(self, book_id: str) -> AuditResult:
        meta = self._load_meta_or_raise(book_id)
        text = self._load_text_or_raise(book_id)
        result = self.audit_runner.run_audit(1, text)
        llm_result = await LLMAuditor(self.llm, self.prompt_registry, self.config).audit(
            chapter_text=text,
            characters=(),
            world=None,
            previous_truth=None,
            extra_context=f"短篇标题：{meta.title}\n短篇类型：{meta.genre}\n核心设定：{meta.premise}",
        )
        result = _merge_llm_audit(result, llm_result)
        self._save_meta(self._with_meta_updates(meta, status=ShortStoryStatus.AUDITED, actual_chars=count_chinese_chars(text)))
        return result

    async def revise(self, book_id: str) -> ShortStoryResult:
        meta = self._load_meta_or_raise(book_id)
        text = self._load_text_or_raise(book_id)
        audit = self.audit_runner.run_audit(1, text)
        failed = [result for result in audit.rule_results if not result.passed]
        if not failed:
            return ShortStoryResult(book_id, ShortStoryStatus.AUDITED, text, audit=audit)
        patch_targets = build_patch_targets(text, failed)
        if not patch_targets:
            return ShortStoryResult(book_id, ShortStoryStatus.AUDITED, text, audit=audit, error="short_revise_failed: no patch targets")
        data = await self.llm.generate_json(
            "short_revise",
            _patch_revision_prompt(),
            {
                "book_id": book_id,
                "mode": "patch",
                "revision_round": 1,
                "failed_rules": tuple(result.rule_id for result in failed),
                "blocking_issues": audit.blocking_issues,
                "patch_targets": tuple(target.__dict__ for target in patch_targets),
                "instruction": "只输出 JSON object。生成 find/replace 局部补丁；不要输出完整短篇。",
            },
            _patch_revision_schema(),
            model=self.config.model_for_task("writer"),
            temperature=0.2,
            max_output_tokens=1200,
            prompt_version="short-patch-revise-v1",
        )
        try:
            patches = validate_patch_response(data)
        except ValueError as exc:
            return ShortStoryResult(book_id, ShortStoryStatus.AUDITED, text, audit=audit, error=str(exc))
        patch_result = apply_patches(text, patches)
        if patch_result.applied_count < 1:
            return ShortStoryResult(book_id, ShortStoryStatus.AUDITED, text, audit=audit, error="short_revise_failed: no patches applied")
        self._save_text(book_id, patch_result.text)
        revised_audit = self.audit_runner.run_audit(1, patch_result.text)
        self._save_meta(self._with_meta_updates(meta, status=ShortStoryStatus.REVISED, actual_chars=count_chinese_chars(patch_result.text)))
        return ShortStoryResult(book_id, ShortStoryStatus.REVISED, patch_result.text, audit=revised_audit)

    async def export(self, book_id: str, fmt: str = "tomato_txt") -> Path:
        meta = self._load_meta_or_raise(book_id)
        fmt = _normalize_format(fmt)
        text = self._load_text_or_raise(book_id)
        path = self._export_path(book_id, fmt)
        if fmt in {"tomato_txt", "tomato", "txt"}:
            self.storage.write_text(path, self.formatter.format_chapter(meta.title, 1, text))
        elif fmt == "md":
            self.storage.write_text(path, f"# {meta.title}\n\n{_normalize_body(text)}")
        elif fmt == "qidian_txt":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(with_utf8_bom(format_qidian_chapter(1, text)))
        elif fmt == "epub":
            write_epub_book(path, book_id=book_id, title=meta.title, chapters=[(1, text)])
        self._save_meta(self._with_meta_updates(meta, status=ShortStoryStatus.EXPORTED, actual_chars=count_chinese_chars(text)))
        return path

    async def run_full_pipeline(self, book_id: str) -> ShortStoryResult:
        await self.plan(book_id)
        text = await self.draft(book_id)
        audit = await self.audit(book_id)
        if not audit.passed:
            revised = await self.revise(book_id)
            text = revised.text
            audit = revised.audit or audit
        await self.export(book_id)
        return ShortStoryResult(book_id, ShortStoryStatus.EXPORTED, text, audit=audit)

    def get_status(self, book_id: str) -> ShortStoryResult | None:
        meta = self._load_meta(book_id)
        if meta is None:
            return None
        text = self.storage.read_text(self._text_path(book_id)) or ""
        audit = self.audit_runner.run_audit(1, text) if text else None
        return ShortStoryResult(book_id, meta.status, text, audit=audit)

    def list_stories(self) -> list[ShortStoryMeta]:
        if not self.paths.books_root.exists():
            return []
        stories: list[ShortStoryMeta] = []
        for book_dir in sorted(path for path in self.paths.books_root.iterdir() if path.is_dir()):
            meta = self._load_meta(book_dir.name)
            if meta is not None:
                stories.append(meta)
        return stories

    def _save_text(self, book_id: str, text: str) -> None:
        self.storage.write_text(self._text_path(book_id), text)

    def _load_meta_or_raise(self, book_id: str) -> ShortStoryMeta:
        meta = self._load_meta(book_id)
        if meta is None:
            raise FileNotFoundError(f"short story not found: {book_id}")
        return meta

    def _load_meta(self, book_id: str) -> ShortStoryMeta | None:
        data = self.storage.read_json(self._meta_path(book_id))
        if not data:
            return None
        return ShortStoryMeta(**{**data, "status": ShortStoryStatus(str(data["status"]))})

    def _save_meta(self, meta: ShortStoryMeta) -> None:
        data = asdict(meta)
        data["status"] = meta.status.value
        self.storage.write_json(self._meta_path(meta.book_id), data)

    def _with_meta_updates(self, meta: ShortStoryMeta, **updates: object) -> ShortStoryMeta:
        data = asdict(meta)
        data["status"] = meta.status
        data.update(updates)
        data["updated_at"] = _now()
        return ShortStoryMeta(**data)

    def _load_plan(self, book_id: str) -> ShortStoryPlan | None:
        data = self.storage.read_json(self._plan_path(book_id))
        if not data:
            return None
        return ShortStoryPlan(
            book_id=str(data.get("book_id", book_id)),
            premise=str(data.get("premise", "")),
            opening=str(data.get("opening", "")),
            climax=str(data.get("climax", "")),
            ending=str(data.get("ending", "")),
            characters=str(data.get("characters", "")),
            key_scenes=tuple(str(item) for item in data.get("key_scenes", ())),
            must_keep=tuple(str(item) for item in data.get("must_keep", ())),
            must_avoid=tuple(str(item) for item in data.get("must_avoid", ())),
        )

    def _load_text_or_raise(self, book_id: str) -> str:
        text = self.storage.read_text(self._text_path(book_id))
        if text is None:
            raise FileNotFoundError(f"short story text not found: {book_id}")
        return text

    def _plan_to_text(self, plan: ShortStoryPlan) -> str:
        return "\n".join(
            [
                f"核心设定：{plan.premise}",
                f"开篇设计：{plan.opening}",
                f"高潮设计：{plan.climax}",
                f"结尾设计：{plan.ending}",
                f"角色：{plan.characters}",
                "关键场景：",
                *[f"- {scene}" for scene in plan.key_scenes],
            ]
        )

    def _meta_path(self, book_id: str) -> Path:
        return self.paths.book_dir(book_id) / "short_story.json"

    def _plan_path(self, book_id: str) -> Path:
        return self.paths.book_dir(book_id) / "short_plan.json"

    def _text_path(self, book_id: str) -> Path:
        return self.paths.book_dir(book_id) / "short_text.md"

    def _export_path(self, book_id: str, fmt: str) -> Path:
        if fmt in {"tomato_txt", "tomato", "txt"}:
            return self.paths.book_dir(book_id) / "exports" / "short.tomato.txt"
        if fmt == "qidian_txt":
            return self.paths.book_dir(book_id) / "exports" / "short-qidian.txt"
        return self.paths.book_dir(book_id) / "exports" / f"short.{fmt}"


def _parse_plan(book_id: str, outline: str, *, fallback_premise: str) -> ShortStoryPlan:
    sections = _markdown_sections(outline)
    return ShortStoryPlan(
        book_id=book_id,
        premise=sections.get("核心设定", fallback_premise).strip() or fallback_premise,
        opening=sections.get("开篇设计", "").strip(),
        climax=sections.get("高潮设计", "").strip(),
        ending=sections.get("结尾设计", "").strip(),
        characters=sections.get("角色", "").strip(),
        key_scenes=tuple(_scene_lines(sections.get("关键场景", ""))),
        must_keep=tuple(_scene_lines(sections.get("必须保留", ""))),
        must_avoid=tuple(_scene_lines(sections.get("必须避免", "不要流水账；不要空泛总结。"))),
    )


def _markdown_sections(text: str) -> dict[str, str]:
    matches = list(re.finditer(r"^##\s*(.+?)\s*$", text, flags=re.MULTILINE))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[match.group(1).strip()] = text[start:end].strip()
    return sections


def _scene_lines(text: str) -> list[str]:
    lines = []
    for raw in text.splitlines():
        line = re.sub(r"^\s*(?:[-*]|\d+[.、)]|第[一二三四五六七八九十]+[场幕])\s*", "", raw).strip()
        if line:
            lines.append(line)
    return lines


def _dump_plan(plan: ShortStoryPlan) -> dict:
    data = asdict(plan)
    data["key_scenes"] = list(plan.key_scenes)
    data["must_keep"] = list(plan.must_keep)
    data["must_avoid"] = list(plan.must_avoid)
    return data


def _merge_llm_audit(mechanical: AuditResult, llm_result: LLMAuditResult) -> AuditResult:
    llm_rules = tuple(_llm_issue_to_rule(index, issue) for index, issue in enumerate(llm_result.issues, start=1))
    rule_results = (*mechanical.rule_results, *llm_rules)
    blocking = tuple(result.rule_id for result in rule_results if not result.passed and result.severity == RuleSeverity.BLOCKING)
    warnings = tuple(result.rule_id for result in rule_results if not result.passed and result.severity == RuleSeverity.WARNING)
    info = tuple(result.rule_id for result in rule_results if not result.passed and result.severity == RuleSeverity.INFO)
    return AuditResult(
        chapter_no=mechanical.chapter_no,
        passed=not blocking,
        blocking_issues=blocking,
        warnings=warnings,
        info=info,
        rule_results=rule_results,
    )


def _llm_issue_to_rule(index: int, issue) -> RuleResult:
    severity = _llm_severity(issue.severity)
    return RuleResult(
        rule_id=f"llm_audit_{index}",
        passed=False,
        severity=severity,
        category=RuleCategory.STRUCTURE,
        message=issue.description,
        detail={"dimension": issue.dimension, "suggestion": issue.suggestion},
    )


def _llm_severity(value: str) -> RuleSeverity:
    if value == "critical":
        return RuleSeverity.BLOCKING
    if value == "info":
        return RuleSeverity.INFO
    return RuleSeverity.WARNING


def _make_short_story_id(title: str) -> str:
    safe = "".join(char.lower() for char in title if char.isascii() and char.isalnum())
    return f"story_{safe or datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"


def _normalize_format(fmt: str) -> str:
    normalized = fmt.strip().lower()
    if normalized not in SUPPORTED_SHORT_EXPORT_FORMATS:
        raise ValueError(f"unsupported export format: {fmt}")
    return normalized


def _normalize_body(text: str) -> str:
    paragraphs = [part.strip() for part in text.replace("\r\n", "\n").split("\n\n") if part.strip()]
    return "\n\n".join(paragraphs)


def _patch_revision_prompt() -> str:
    return (
        "你是中文短篇小说局部修订器。只输出 JSON object。"
        "根据 patch_targets 生成 find/replace 补丁。"
        "find 必须逐字来自对应 window_text，replace 只包含替换后的小说正文。"
        "禁止输出完整短篇，禁止解释。"
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
