from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from storyforge3.config import StoryForge3Config
from storyforge3.models import Character, TruthData, WorldConfig
from storyforge3.prompts.registry import PromptRegistry


AUDIT_DIMENSIONS = (
    "OOC 检查",
    "战力一致性",
    "信息边界",
    "情节逻辑",
    "节奏检查",
    "钩子检查",
    "断章检查",
    "Show Don't Tell",
    "AI 痕迹",
    "流水账检查",
)
ISSUE_SEVERITIES = {"critical", "warning", "info"}


@dataclass(frozen=True)
class LLMAuditIssue:
    severity: str
    dimension: str
    description: str
    suggestion: str


@dataclass(frozen=True)
class LLMAuditResult:
    passed: bool
    issues: tuple[LLMAuditIssue, ...]


class LLMAuditor:
    def __init__(self, llm: Any, registry: PromptRegistry, config: StoryForge3Config) -> None:
        self.llm = llm
        self.registry = registry
        self.config = config

    async def audit(
        self,
        *,
        chapter_text: str,
        characters: tuple[Character, ...],
        world: WorldConfig | None,
        previous_truth: TruthData | None,
        extra_context: str = "",
        extra_dimensions: tuple[str, ...] = (),
    ) -> LLMAuditResult:
        template = self.registry.get_latest("llm_audit")
        dimensions = (*AUDIT_DIMENSIONS, *extra_dimensions)
        data = await self.llm.generate_json(
            "llm_audit",
            self.registry.render_system_prompt(template),
            self._payload(chapter_text, characters, world, previous_truth, extra_context, dimensions),
            self._schema(),
            model=self.config.model_for_task("auditor"),
            prompt_version=f"{template.prompt_id}:v{template.version}",
        )
        issues = tuple(self._parse_issue(item, dimensions) for item in data.get("issues", ()) if isinstance(item, dict))
        critical = any(issue.severity == "critical" for issue in issues)
        return LLMAuditResult(passed=not critical, issues=issues)

    @staticmethod
    def _payload(
        chapter_text: str,
        characters: tuple[Character, ...],
        world: WorldConfig | None,
        previous_truth: TruthData | None,
        extra_context: str,
        dimensions: tuple[str, ...],
    ) -> dict:
        return {
            "dimensions": list(dimensions),
            "chapter_text": chapter_text,
            "characters": [asdict(character) for character in characters],
            "world_setting": world.setting if world else "",
            "power_system": world.power_system if world else "",
            "world_rules": list(world.rules) if world else [],
            "previous_truth": list(previous_truth.fact_assertions) if previous_truth else [],
            "context": extra_context,
        }

    @staticmethod
    def _parse_issue(data: dict, dimensions: tuple[str, ...] = AUDIT_DIMENSIONS) -> LLMAuditIssue:
        severity = str(data.get("severity") or "warning").strip().lower()
        if severity not in ISSUE_SEVERITIES:
            severity = "warning"
        dimension = str(data.get("dimension") or "情节逻辑").strip()
        aliases = {"OOC": "OOC 检查"}
        dimension = aliases.get(dimension, dimension)
        if dimension not in dimensions:
            dimension = "情节逻辑"
        return LLMAuditIssue(
            severity=severity,
            dimension=dimension,
            description=str(data.get("description") or "").strip(),
            suggestion=str(data.get("suggestion") or "").strip(),
        )

    @staticmethod
    def _schema() -> dict:
        return {
            "type": "object",
            "properties": {
                "issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "severity": {"type": "string"},
                            "dimension": {"type": "string"},
                            "description": {"type": "string"},
                            "suggestion": {"type": "string"},
                        },
                        "required": ["severity", "dimension", "description", "suggestion"],
                    },
                }
            },
            "required": ["issues"],
        }
