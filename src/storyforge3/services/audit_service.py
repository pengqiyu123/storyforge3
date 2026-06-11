from __future__ import annotations

from pathlib import Path
from typing import Any

from storyforge3.audit.llm_auditor import LLMAuditor, LLMAuditResult
from storyforge3.audit.runner import AuditRunner
from storyforge3.config import StoryForge3Config
from storyforge3.fanfic.dimensions import FANFIC_DIMENSIONS, get_fanfic_dimension_config
from storyforge3.fanfic.prompt_sections import build_character_voice_profiles, build_fanfic_canon_section, build_fanfic_mode_instructions
from storyforge3.llm.factory import create_llm_service
from storyforge3.models import AuditResult, FanficCanon, FanficMode
from storyforge3.prompts.registry import PromptRegistry, create_default_registry
from storyforge3.storage import BookStorage, StoragePaths
from storyforge3.style.contract import StyleContract


class AuditService:
    """质量审计服务：机械规则 + LLM 深度审计。"""

    def __init__(
        self,
        *,
        config: StoryForge3Config,
        audit_runner: AuditRunner | None = None,
        llm_auditor: Any | None = None,
        registry: PromptRegistry | None = None,
        style_contract: StyleContract | None = None,
    ) -> None:
        self.config = config
        self._runner = audit_runner or AuditRunner(style_contract)
        self._registry = registry or create_default_registry()
        self._llm_auditor = llm_auditor
        self._paths = StoragePaths(Path(config.books_dir))
        self._storage = BookStorage(self._paths.books_root)

    def run_mechanical(self, chapter_no: int, text: str) -> AuditResult:
        """运行机械审计规则。"""
        return self._runner.run_audit(chapter_no, text)

    async def run_llm_audit(
        self,
        text: str,
        context: str,
        *,
        model: str | None = None,
        book_id: str | None = None,
    ) -> LLMAuditResult:
        """运行 LLM 4 维度审计。"""
        del model
        auditor = self._llm_auditor
        if auditor is None:
            auditor = LLMAuditor(create_llm_service(self.config), self._registry, self.config)
            self._llm_auditor = auditor
        extra_dimensions: tuple[str, ...] = ()
        extra_context = context
        if book_id:
            fanfic_context, extra_dimensions = self._fanfic_audit_context(book_id)
            if fanfic_context:
                extra_context = "\n\n".join(part for part in (context, fanfic_context) if part)
        return await auditor.audit(
            chapter_text=text,
            characters=(),
            world=None,
            previous_truth=None,
            extra_context=extra_context,
            extra_dimensions=extra_dimensions,
        )

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
        data = self._storage.read_json(self._paths.book_meta(book_id)) or {}
        value = str(data.get("fanfic_mode") or "").strip()
        if not value:
            return None
        try:
            return FanficMode(value)
        except ValueError:
            return None

    def _load_fanfic_canon(self, book_id: str) -> FanficCanon | None:
        data = self._storage.read_json(self._paths.book_dir(book_id) / "fanfic_canon.json")
        if not data:
            return None
        try:
            return FanficCanon(**{**data, "mode": FanficMode(str(data.get("mode", "")))})
        except ValueError:
            return None
