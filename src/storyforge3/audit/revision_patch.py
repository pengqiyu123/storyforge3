from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from storyforge3.audit.chinese_text import split_paragraphs
from storyforge3.audit.chinese_text import has_unbalanced_pairs
from storyforge3.models import RuleResult

MAX_PATCH_TARGETS = 4

_FORBIDDEN_TERMS = ("请注意", "以下是", "作为AI", "我是AI")
_ENGINE_TERMS = ("StoryForge", "artifact", "snapshot", "import marker", "生产工作区")
_AI_TELL_TERMS = ("综上", "显然", "总而言之", "值得注意的是", "不可否认", "从某种意义上")
_HEDGE_TERMS = ("似乎", "仿佛", "好像", "某种", "一点点", "几乎")
_DIDACTIC_TERMS = ("应该", "必须", "核心", "关键")

_RULE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "forbidden_patterns": _FORBIDDEN_TERMS,
    "internal_engine_terms": _ENGINE_TERMS,
    "output_leak": ("```", "JSON", "Markdown"),
    "html_or_xml_leak": ("<", ">"),
    "markdown_artifacts": ("#", "**"),
    "sensitive_placeholder": ("TODO", "FIXME", "占位"),
    "ai_tell_density": _AI_TELL_TERMS,
    "hedge_density": _HEDGE_TERMS,
    "didactic_words": _DIDACTIC_TERMS,
    "meta_narration_patterns": ("本章", "读者", "作者"),
    "explanatory_patterns": ("这说明", "也就是说", "换句话说"),
    "meta_patterns": ("接下来", "下一章", "剧情"),
    "report_terms": ("风险", "策略", "评估", "执行"),
}


@dataclass(frozen=True)
class PatchTarget:
    rule_id: str
    reason: str
    window_text: str
    allowed_change: str


@dataclass(frozen=True)
class TextPatch:
    find: str
    replace: str
    rule_id: str = ""


@dataclass(frozen=True)
class PatchFailure:
    rule_id: str
    find: str
    reason: str


@dataclass(frozen=True)
class PatchApplyResult:
    text: str
    applied_count: int
    failed_count: int
    failures: tuple[PatchFailure, ...]


def build_patch_targets(text: str, failed_rules: list[RuleResult | dict]) -> tuple[PatchTarget, ...]:
    paragraphs = split_paragraphs(text)
    targets: list[PatchTarget] = []
    seen: set[tuple[str, str]] = set()
    for rule in failed_rules:
        rule_id = _rule_id(rule)
        if not rule_id:
            continue
        window = _window_for_rule(rule, rule_id, paragraphs)
        if not window:
            continue
        key = (rule_id, window)
        if key in seen:
            continue
        seen.add(key)
        targets.append(
            PatchTarget(
                rule_id=rule_id,
                reason=_message(rule),
                window_text=window,
                allowed_change=_allowed_change(rule_id),
            )
        )
        if len(targets) >= MAX_PATCH_TARGETS:
            break
    return tuple(targets)


def validate_patch_response(data: dict[str, Any]) -> tuple[TextPatch, ...]:
    raw_patches = data.get("patches")
    if isinstance(raw_patches, list):
        items = raw_patches
    elif isinstance(data.get("find"), str) and isinstance(data.get("replace"), str):
        items = [data]
    else:
        raise ValueError("patch response must contain patches list")

    patches: list[TextPatch] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        find = str(item.get("find") or "").strip()
        replace = str(item.get("replace") or "").strip()
        if not find or not replace or find == replace:
            continue
        patches.append(TextPatch(find, replace, str(item.get("rule_id") or "").strip()))
    if not patches:
        raise ValueError("patch response contains no valid patches")
    return tuple(patches)


def apply_patches(text: str, patches: tuple[TextPatch, ...]) -> PatchApplyResult:
    current = text
    applied = 0
    failures: list[PatchFailure] = []
    for patch in patches:
        if patch.find not in current:
            failures.append(PatchFailure(patch.rule_id, patch.find, "find not found"))
            continue
        current = current.replace(patch.find, patch.replace, 1)
        applied += 1
    return PatchApplyResult(
        text=current,
        applied_count=applied,
        failed_count=len(failures),
        failures=tuple(failures),
    )


def _window_for_rule(rule: RuleResult | dict, rule_id: str, paragraphs: list[str]) -> str:
    if not paragraphs:
        return ""
    if rule_id == "golden_three_hook":
        return _join(paragraphs[:3])
    if rule_id == "cliffhanger_presence":
        return _join(paragraphs[-3:])
    if rule_id == "below_min_word_count":
        return _join(paragraphs[-3:])
    if rule_id == "unbalanced_quote_or_bracket":
        matched = [paragraph for paragraph in paragraphs if has_unbalanced_pairs(paragraph)]
        return _join(matched[:2] or paragraphs[: min(3, len(paragraphs))])

    keywords = _keywords_for_rule(rule, rule_id)
    matched_indexes = [index for index, paragraph in enumerate(paragraphs) if any(keyword in paragraph for keyword in keywords)]
    if matched_indexes:
        index = matched_indexes[0]
        start = max(0, index - 1)
        end = min(len(paragraphs), index + 2)
        return _join(paragraphs[start:end])
    return _join(paragraphs[: min(3, len(paragraphs))])


def _keywords_for_rule(rule: RuleResult | dict, rule_id: str) -> tuple[str, ...]:
    keywords: list[str] = []
    detail = _detail(rule)
    for key in ("keywords", "found"):
        value = detail.get(key)
        if isinstance(value, list):
            keywords.extend(str(item) for item in value if str(item).strip())
        elif isinstance(value, tuple):
            keywords.extend(str(item) for item in value if str(item).strip())
    phrases = detail.get("phrases")
    if isinstance(phrases, list):
        for item in phrases:
            if isinstance(item, (list, tuple)) and item:
                keywords.append(str(item[0]))
            else:
                keywords.append(str(item))
    keywords.extend(_RULE_KEYWORDS.get(rule_id, ()))
    return tuple(dict.fromkeys(keyword.strip() for keyword in keywords if keyword.strip()))


def _allowed_change(rule_id: str) -> str:
    if rule_id == "golden_three_hook":
        return (
            "只改前三段之一，加入有效钩子。"
            "有效钩子至少满足以下两种："
            "（1）≤10字的短句冲击段；"
            "（2）异常/变化词（如鼓起、裂开、消失、凝固等）；"
            "（3）对话引号或拟声词；"
            "（4）悬念标点？或！。"
        )
    if rule_id == "cliffhanger_presence":
        return "只改章尾窗口，补足章尾悬念。"
    if rule_id == "below_min_word_count":
        return "只扩写窗口内段落，不改变既有事实。"
    if rule_id == "unbalanced_quote_or_bracket":
        return "只修复引号或括号配对。"
    if rule_id in {"forbidden_patterns", "output_leak", "html_or_xml_leak", "markdown_artifacts"}:
        return "只移除或改写泄露/格式残留，不改变剧情。"
    return "只修复当前规则涉及的局部文本，不改无关段落。"


def _rule_id(rule: RuleResult | dict) -> str:
    if isinstance(rule, RuleResult):
        return rule.rule_id
    return str(rule.get("rule_id", "")).strip()


def _message(rule: RuleResult | dict) -> str:
    if isinstance(rule, RuleResult):
        return rule.message
    return str(rule.get("message") or "")


def _detail(rule: RuleResult | dict) -> dict[str, Any]:
    if isinstance(rule, RuleResult):
        return rule.detail
    detail = rule.get("detail")
    return detail if isinstance(detail, dict) else {}


def _join(paragraphs: list[str]) -> str:
    return "\n\n".join(paragraph.strip() for paragraph in paragraphs if paragraph.strip())
