from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from storyforge3.models import RuleCategory, RuleResult, RuleSeverity


class RevisionMode(str, Enum):
    POLISH = "polish"
    SPOT_FIX = "spot_fix"
    ANTI_DETECT = "anti-detect"
    SURGICAL = "surgical"
    REWORK = "rework"


@dataclass(frozen=True)
class RevisionModeConfig:
    mode: RevisionMode
    description: str
    allowed_rule_categories: tuple[str, ...]
    forbidden_actions: tuple[str, ...] = ()
    generation_config_overrides: dict = field(default_factory=dict)
    prompt_constraints: tuple[str, ...] = ()


MODE_CONFIGS: dict[RevisionMode, RevisionModeConfig] = {
    RevisionMode.POLISH: RevisionModeConfig(
        mode=RevisionMode.POLISH,
        description="风格优化，不改情节和事实。",
        allowed_rule_categories=("style", "ai_tell"),
        forbidden_actions=("改写对话内容", "调整场景顺序", "增删角色"),
        generation_config_overrides={"temperature": 0.7, "frequency_penalty": 0.2},
        prompt_constraints=(
            "只改措辞和表达，不改任何事实、剧情走向和角色行为。",
            "保持原文段落数和大致结构不变。",
            "每次修改限制在单句或相邻两句范围内。",
        ),
    ),
    RevisionMode.SPOT_FIX: RevisionModeConfig(
        mode=RevisionMode.SPOT_FIX,
        description="精准修复少量结构/风格问题。",
        allowed_rule_categories=("structure", "style"),
        forbidden_actions=("大面积改写", "调整非失败段落"),
        generation_config_overrides={"temperature": 0.65},
        prompt_constraints=(
            "只修复标注的失败规则，不碰其他段落。",
            "改动范围控制在涉及段落内，不扩散到相邻正常段落。",
            "如果修复 pacing_flat，只增删转折标记，不改已有内容。",
            "如果修复 cliffhanger_presence，只在章尾追加，不改章中。",
        ),
    ),
    RevisionMode.ANTI_DETECT: RevisionModeConfig(
        mode=RevisionMode.ANTI_DETECT,
        description="去除 AI 痕迹专用，只处理 ai_tell 类问题。",
        allowed_rule_categories=("ai_tell",),
        forbidden_actions=("改写剧情", "调整节奏", "修改对话内容"),
        generation_config_overrides={"temperature": 0.9, "presence_penalty": 0.25},
        prompt_constraints=(
            "只消除AI痕迹，不做任何其他修改。",
            "替换词应保持原意，不降低信息密度。",
            "不要为了去AI味而引入新的模式化表达。",
            "禁止机械地每句都改，只改触发规则的句子。",
        ),
    ),
    RevisionMode.SURGICAL: RevisionModeConfig(
        mode=RevisionMode.SURGICAL,
        description="混合问题的多点精准修复。",
        allowed_rule_categories=("structure", "style", "ai_tell", "meta"),
    ),
    RevisionMode.REWORK: RevisionModeConfig(
        mode=RevisionMode.REWORK,
        description="结构性或阻断问题的全文重写。",
        allowed_rule_categories=("structure", "style", "ai_tell", "meta"),
        generation_config_overrides={"temperature": 0.92},
        prompt_constraints=(
            "保留核心事实和已提交真相。",
            "保留主角身份和当前场景设定。",
        ),
    ),
}


RULE_CATEGORIES: dict[str, str] = {
    "meta_narration_patterns": "ai_tell",
    "didactic_words": "ai_tell",
    "explanatory_patterns": "ai_tell",
    "ai_tell_density": "ai_tell",
    "meta_patterns": "ai_tell",
    "report_terms": "ai_tell",
    "template_emotion": "ai_tell",
    "action_sentence_ratio": "style",
    "repeated_phrase": "style",
    "dialogue_density": "style",
    "golden_three_hook": "structure",
    "show_dont_tell": "style",
    "hedge_density": "style",
    "surprise_word_density": "style",
    "vague_word_density": "style",
    "sentence_start_repetition": "style",
    "paragraph_ending_repetition": "style",
    "pacing_flat": "structure",
    "cliffhanger_presence": "structure",
    "info_dump": "structure",
    "paragraph_count": "structure",
    "max_paragraph_length": "structure",
    "unbalanced_quote_or_bracket": "structure",
    "scene_anchor_presence": "structure",
    "conflict_presence": "structure",
    "sensory_detail_presence": "structure",
    "chapter_word_count": "meta",
    "below_min_word_count": "meta",
    "empty_text": "meta",
    "internal_engine_terms": "meta",
    "forbidden_patterns": "meta",
    "title_keyword_repeat": "meta",
    "output_leak": "meta",
    "html_or_xml_leak": "meta",
    "markdown_artifacts": "meta",
    "sensitive_placeholder": "meta",
}

REWORK_BLOCKING_RULES = frozenset({"empty_text"})
SURGICAL_BLOCKING_RULES = frozenset({"below_min_word_count"})
SPOT_FIX_BLOCKING_RULES = frozenset(
    {
        "unbalanced_quote_or_bracket",
        "forbidden_patterns",
        "golden_three_hook",
    }
)
LOCAL_BLOCKING_RULES = SURGICAL_BLOCKING_RULES | SPOT_FIX_BLOCKING_RULES


def get_mode_config(mode: RevisionMode | str) -> RevisionModeConfig:
    return MODE_CONFIGS[RevisionMode(mode)]


class RevisionModeRecommender:
    """Recommend a deterministic revision mode from audit failures."""

    def recommend(
        self,
        failed_rules: list[RuleResult | dict],
        blocking_count: int,
        revision_round: int,
    ) -> RevisionMode:
        grouped = self.categorize_failures(failed_rules)
        categories = {category for category, rules in grouped.items() if rules}
        if not categories:
            return RevisionMode.SURGICAL
        if blocking_count > 0:
            return self._recommend_blocking(failed_rules)
        if categories == {"ai_tell"}:
            return RevisionMode.ANTI_DETECT
        if categories == {"style"} and blocking_count == 0:
            return RevisionMode.POLISH
        if len(failed_rules) <= 2 and categories <= {"structure", "style"}:
            return RevisionMode.SPOT_FIX
        return RevisionMode.SURGICAL

    def categorize_failures(self, failed_rules: list[RuleResult | dict]) -> dict[str, tuple[str, ...]]:
        grouped: dict[str, list[str]] = {
            "ai_tell": [],
            "style": [],
            "structure": [],
            "meta": [],
            "unknown": [],
        }
        for rule in failed_rules:
            rule_id = self._rule_id(rule)
            if not rule_id:
                continue
            category = self._category(rule, rule_id)
            grouped.setdefault(category, []).append(rule_id)
        return {category: tuple(rules) for category, rules in grouped.items()}

    @staticmethod
    def failed_results(audit_results: tuple[RuleResult, ...]) -> list[RuleResult]:
        return [result for result in audit_results if not result.passed]

    @staticmethod
    def blocking_count(failed_rules: list[RuleResult | dict]) -> int:
        return sum(1 for rule in failed_rules if RevisionModeRecommender._severity(rule) == RuleSeverity.BLOCKING.value)

    def _recommend_blocking(self, failed_rules: list[RuleResult | dict]) -> RevisionMode:
        blocking_rule_ids = self._blocking_rule_ids(failed_rules)
        if not blocking_rule_ids:
            return RevisionMode.SURGICAL
        blocking_set = set(blocking_rule_ids)
        if blocking_set & REWORK_BLOCKING_RULES:
            return RevisionMode.REWORK
        if blocking_set <= SPOT_FIX_BLOCKING_RULES and len(blocking_rule_ids) <= 2:
            return RevisionMode.SPOT_FIX
        if blocking_set <= LOCAL_BLOCKING_RULES:
            return RevisionMode.SURGICAL
        return RevisionMode.SURGICAL

    @staticmethod
    def _blocking_rule_ids(failed_rules: list[RuleResult | dict]) -> tuple[str, ...]:
        return tuple(
            rule_id
            for rule in failed_rules
            if RevisionModeRecommender._severity(rule) == RuleSeverity.BLOCKING.value
            for rule_id in (RevisionModeRecommender._rule_id(rule),)
            if rule_id
        )

    @staticmethod
    def _rule_id(rule: RuleResult | dict) -> str:
        if isinstance(rule, RuleResult):
            return rule.rule_id
        return str(rule.get("rule_id", "")).strip()

    @staticmethod
    def _category(rule: RuleResult | dict, rule_id: str) -> str:
        if isinstance(rule, RuleResult):
            category = rule.category.value
        else:
            raw = rule.get("category")
            category = raw.value if isinstance(raw, RuleCategory) else str(raw or "")
        normalized = category.strip().replace("-", "_")
        return normalized if normalized in {"ai_tell", "style", "structure", "meta"} else RULE_CATEGORIES.get(rule_id, "unknown")

    @staticmethod
    def _severity(rule: RuleResult | dict) -> str:
        if isinstance(rule, RuleResult):
            return rule.severity.value
        raw = rule.get("severity")
        return raw.value if isinstance(raw, RuleSeverity) else str(raw or "")
