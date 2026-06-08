from __future__ import annotations

import re
from collections.abc import Callable

from storyforge3.audit.chinese_text import (
    count_chinese_chars,
    density,
    has_unbalanced_pairs,
    max_quiet_paragraph_run,
    regex_count,
    repeated_phrases,
    sentence_ratio,
)
from storyforge3.audit.context import MechanicalContext
from storyforge3.audit import thresholds as T
from storyforge3.models import RuleCategory, RuleResult, RuleSeverity


AI_TELL_WORDS = ("综上", "显然", "总而言之", "值得注意的是", "不可否认", "从某种意义上")
HEDGE_WORDS = ("似乎", "仿佛", "好像", "某种", "一点点", "几乎")
ACTION_WORDS = ("走进", "走出", "看向", "盯着", "坐下", "站起", "拿出", "放下", "打开", "接过", "伸出", "低头", "抬眼", "靠近", "退后", "停下")
TURN_MARKERS = ("但", "却", "可是", "不过", "突然", "不料", "谁知", "下一秒", "下一刻", "意识到", "随即", "紧接着", "与此同时", "发现")
ENGINE_TERMS = ("StoryForge", "artifact", "snapshot", "import marker", "生产工作区")
HOOK_KEYWORDS = ("突然", "不对", "异常", "发现", "声音", "门")
HOOK_ABNORMAL_CHANGE_WORDS = (
    "鼓起",
    "裂开",
    "炸开",
    "碎裂",
    "脱落",
    "塌陷",
    "变形",
    "扭曲",
    "渗出",
    "浮现",
    "冒出",
    "伸出",
    "缩回",
    "爬行",
    "滚动",
    "坠落",
    "弹开",
    "崩塌",
    "敲掉",
    "撕裂",
    "砸",
    "撞",
    "刺",
    "劈",
    "拽",
    "拖",
    "扼",
    "掐住",
    "消失",
    "凝固",
    "冻结",
    "燃烧",
    "熄灭",
    "断裂",
    "错位",
    "脱位",
)
HOOK_QUOTE_MARKS = ("“", "”", "「", "」", "『", "』", '"')
HOOK_SOUND_CHARS = frozenset("叩咚咔嗒滴答轰砰啪哗沙嗡铃嘀吱嘎咯")
HOOK_SOUND_PATTERN = re.compile(r"([\u4e00-\u9fff]{2,4})\1|([\u4e00-\u9fff])\2+")


def make_result(rule_id: str, passed: bool, severity: RuleSeverity, category: RuleCategory, message: str, **detail) -> RuleResult:
    return RuleResult(rule_id, passed, severity, category, message, detail)


def check_empty_text(ctx: MechanicalContext) -> RuleResult:
    return make_result("empty_text", bool(ctx.text.strip()), RuleSeverity.BLOCKING, RuleCategory.INTEGRITY, "正文不能为空")


def check_below_min_word_count(ctx: MechanicalContext) -> RuleResult:
    return make_result("below_min_word_count", ctx.chinese_chars >= T.MIN_CHINESE_CHARS, RuleSeverity.BLOCKING, RuleCategory.INTEGRITY, "中文字数不足", observed=ctx.chinese_chars)


def check_chapter_word_count(ctx: MechanicalContext) -> RuleResult:
    return make_result("chapter_word_count", ctx.chinese_chars >= T.MIN_CHINESE_CHARS, RuleSeverity.WARNING, RuleCategory.META, "章节中文字数偏低", observed=ctx.chinese_chars)


def check_unbalanced_quote_or_bracket(ctx: MechanicalContext) -> RuleResult:
    return make_result("unbalanced_quote_or_bracket", not has_unbalanced_pairs(ctx.text), RuleSeverity.BLOCKING, RuleCategory.INTEGRITY, "引号或括号不平衡")


def check_forbidden_patterns(ctx: MechanicalContext) -> RuleResult:
    bad = ("请注意", "以下是", "作为AI", "我是AI")
    found = [word for word in bad if word in ctx.text]
    return make_result("forbidden_patterns", not found, RuleSeverity.BLOCKING, RuleCategory.META, "含禁止输出模式", found=found)


def check_golden_three_hook(ctx: MechanicalContext) -> RuleResult:
    head_paragraphs = list(ctx.paragraphs[:3])
    head = "\n".join(head_paragraphs)
    checks = {
        "short_impact": _has_short_impact_paragraph(head_paragraphs),
        "abnormal_change": any(word in head for word in HOOK_ABNORMAL_CHANGE_WORDS),
        "dialogue_or_sound": _has_dialogue_or_sound(head),
        "suspense_punctuation": any(mark in head for mark in ("？", "！")),
    }
    keyword_hits = sum(1 for marker in HOOK_KEYWORDS if marker in head)
    score = sum(1 for passed in checks.values() if passed) + min(keyword_hits, 2)
    return make_result(
        "golden_three_hook",
        score >= 2,
        RuleSeverity.BLOCKING,
        RuleCategory.STRUCTURE,
        "前三段缺少有效钩子",
        score=score,
        matched_dimensions=[name for name, passed in checks.items() if passed],
        keyword_hits=keyword_hits,
    )


def _has_short_impact_paragraph(paragraphs: list[str]) -> bool:
    return any(0 < count_chinese_chars(paragraph) <= 10 for paragraph in paragraphs)


def _has_dialogue_or_sound(text: str) -> bool:
    if any(mark in text for mark in HOOK_QUOTE_MARKS):
        return True
    for match in HOOK_SOUND_PATTERN.finditer(text):
        token = next((group for group in match.groups() if group), "")
        if any(char in HOOK_SOUND_CHARS for char in token):
            return True
    return False


def check_internal_engine_terms(ctx: MechanicalContext) -> RuleResult:
    found = [word for word in ENGINE_TERMS if word in ctx.text]
    return make_result("internal_engine_terms", not found, RuleSeverity.WARNING, RuleCategory.META, "泄露内部工程术语", found=found)


def check_ai_tell_density(ctx: MechanicalContext) -> RuleResult:
    value = density(ctx.text, AI_TELL_WORDS)
    return make_result("ai_tell_density", value <= 2.0, RuleSeverity.WARNING, RuleCategory.AI_TELL, "AI解释腔偏高", observed=value)


def check_hedge_density(ctx: MechanicalContext) -> RuleResult:
    value = density(ctx.text, HEDGE_WORDS)
    return make_result("hedge_density", value <= T.MAX_HEDGE_DENSITY, RuleSeverity.WARNING, RuleCategory.STYLE, "模糊词密度偏高", observed=value)


def check_action_sentence_ratio(ctx: MechanicalContext) -> RuleResult:
    value = sentence_ratio(list(ctx.sentences), ACTION_WORDS)
    return make_result("action_sentence_ratio", value >= T.MIN_ACTION_SENTENCE_RATIO, RuleSeverity.WARNING, RuleCategory.STYLE, "动作句占比偏低", observed=value)


def check_pacing_flat(ctx: MechanicalContext) -> RuleResult:
    value = max_quiet_paragraph_run(list(ctx.paragraphs), TURN_MARKERS)
    return make_result("pacing_flat", value < T.MAX_PACING_FLAT_RUN, RuleSeverity.WARNING, RuleCategory.STRUCTURE, "连续平段过长", observed=value)


def check_repeated_phrase(ctx: MechanicalContext) -> RuleResult:
    phrases = repeated_phrases(ctx.text)
    return make_result("repeated_phrase", len(phrases) <= T.MAX_REPEATED_PHRASES, RuleSeverity.WARNING, RuleCategory.STYLE, "重复短语过多", phrases=phrases[:5])


def check_dialogue_density(ctx: MechanicalContext) -> RuleResult:
    quote_count = ctx.text.count("“") + ctx.text.count('"')
    ratio = quote_count / max(len(ctx.sentences), 1)
    return make_result("dialogue_density", ratio >= T.MIN_DIALOGUE_RATIO, RuleSeverity.WARNING, RuleCategory.STYLE, "对话密度偏低", observed=ratio)


def check_info_dump(ctx: MechanicalContext) -> RuleResult:
    longest = max((len(p) for p in ctx.paragraphs), default=0)
    return make_result("info_dump", longest <= T.MAX_INFO_DUMP_PARAGRAPH_CHARS, RuleSeverity.WARNING, RuleCategory.STRUCTURE, "长段信息倾倒", observed=longest)


def check_paragraph_count(ctx: MechanicalContext) -> RuleResult:
    return make_result("paragraph_count", len(ctx.paragraphs) >= T.MIN_PARAGRAPHS, RuleSeverity.WARNING, RuleCategory.STRUCTURE, "段落数偏少", observed=len(ctx.paragraphs))


def check_cliffhanger_presence(ctx: MechanicalContext) -> RuleResult:
    tail = "\n".join(ctx.paragraphs[-3:])
    passed = any(mark in tail for mark in ("？", "！", "突然", "下一秒", "停了下来", "门", "声音"))
    return make_result("cliffhanger_presence", passed, RuleSeverity.WARNING, RuleCategory.STRUCTURE, "章尾钩子不足")


def check_max_paragraph_length(ctx: MechanicalContext) -> RuleResult:
    longest = max((len(p) for p in ctx.paragraphs), default=0)
    return make_result("max_paragraph_length", longest <= T.MAX_PARAGRAPH_CHARS, RuleSeverity.WARNING, RuleCategory.STYLE, "段落过长", observed=longest)


def regex_rule(rule_id: str, pattern: str, category: RuleCategory, message: str, max_count: int = 0) -> Callable[[MechanicalContext], RuleResult]:
    def check(ctx: MechanicalContext) -> RuleResult:
        count = regex_count(ctx.text, pattern)
        return make_result(rule_id, count <= max_count, RuleSeverity.WARNING, category, message, observed=count)

    return check


def keyword_rule(rule_id: str, words: tuple[str, ...], category: RuleCategory, message: str, max_hits: int) -> Callable[[MechanicalContext], RuleResult]:
    def check(ctx: MechanicalContext) -> RuleResult:
        hits = sum(ctx.text.count(word) for word in words)
        return make_result(rule_id, hits <= max_hits, RuleSeverity.WARNING, category, message, observed=hits)

    return check


RULE_REGISTRY: dict[str, Callable[[MechanicalContext], RuleResult]] = {
    "empty_text": check_empty_text,
    "below_min_word_count": check_below_min_word_count,
    "unbalanced_quote_or_bracket": check_unbalanced_quote_or_bracket,
    "forbidden_patterns": check_forbidden_patterns,
    "golden_three_hook": check_golden_three_hook,
    "internal_engine_terms": check_internal_engine_terms,
    "ai_tell_density": check_ai_tell_density,
    "hedge_density": check_hedge_density,
    "action_sentence_ratio": check_action_sentence_ratio,
    "pacing_flat": check_pacing_flat,
    "repeated_phrase": check_repeated_phrase,
    "dialogue_density": check_dialogue_density,
    "info_dump": check_info_dump,
    "paragraph_count": check_paragraph_count,
    "cliffhanger_presence": check_cliffhanger_presence,
    "max_paragraph_length": check_max_paragraph_length,
    "meta_narration_patterns": regex_rule("meta_narration_patterns", r"本章|读者|作者", RuleCategory.AI_TELL, "元叙事痕迹"),
    "didactic_words": keyword_rule("didactic_words", ("应该", "必须", "核心", "关键"), RuleCategory.AI_TELL, "说教词偏多", 30),
    "explanatory_patterns": regex_rule("explanatory_patterns", r"这说明|也就是说|换句话说", RuleCategory.AI_TELL, "解释腔"),
    "meta_patterns": regex_rule("meta_patterns", r"接下来|下一章|剧情", RuleCategory.AI_TELL, "剧情说明泄露"),
    "report_terms": keyword_rule("report_terms", ("风险", "策略", "评估", "执行"), RuleCategory.AI_TELL, "报告词泄露", 20),
    "template_emotion": keyword_rule("template_emotion", ("心头一震", "瞳孔一缩", "倒吸一口凉气"), RuleCategory.STYLE, "模板情绪", 2),
    "show_dont_tell": keyword_rule("show_dont_tell", ("很震惊", "很害怕", "很开心"), RuleCategory.STYLE, "直白情绪", 3),
    "surprise_word_density": keyword_rule("surprise_word_density", ("突然", "猛地", "骤然"), RuleCategory.STYLE, "突发词过密", 20),
    "vague_word_density": keyword_rule("vague_word_density", ("东西", "事情", "感觉"), RuleCategory.STYLE, "泛词过多", 35),
    "sentence_start_repetition": regex_rule("sentence_start_repetition", r"(林默[^。！？]{0,8}[。！？]){5,}", RuleCategory.STYLE, "句首重复"),
    "paragraph_ending_repetition": regex_rule("paragraph_ending_repetition", r"(。\\s*){20,}", RuleCategory.STYLE, "段尾节奏重复"),
    "title_keyword_repeat": regex_rule("title_keyword_repeat", r"标题|题目", RuleCategory.META, "标题关键词泄露"),
    "chapter_word_count": check_chapter_word_count,
    "output_leak": regex_rule("output_leak", r"```|JSON|Markdown", RuleCategory.META, "输出格式泄露"),
    "html_or_xml_leak": regex_rule("html_or_xml_leak", r"<[^>]+>", RuleCategory.META, "HTML/XML 泄露"),
    "markdown_artifacts": regex_rule("markdown_artifacts", r"^#{1,6}\s|\*\*", RuleCategory.META, "Markdown 残留"),
    "sensitive_placeholder": regex_rule("sensitive_placeholder", r"TODO|FIXME|占位", RuleCategory.META, "占位符残留"),
    "scene_anchor_presence": keyword_rule("scene_anchor_presence", ("门", "走廊", "房间", "学校", "中心"), RuleCategory.STRUCTURE, "场景锚点不足", 9999),
    "conflict_presence": keyword_rule("conflict_presence", ("不对", "异常", "危险", "失控", "停"), RuleCategory.STRUCTURE, "冲突信号不足", 9999),
    "sensory_detail_presence": keyword_rule("sensory_detail_presence", ("声音", "光", "冷", "热", "脚步"), RuleCategory.STRUCTURE, "感官细节不足", 9999),
}

BLOCKING_RULES = {"empty_text", "below_min_word_count", "unbalanced_quote_or_bracket", "forbidden_patterns", "golden_three_hook"}

for rule_id in ("scene_anchor_presence", "conflict_presence", "sensory_detail_presence"):
    original = RULE_REGISTRY[rule_id]

    def positive_rule(ctx: MechanicalContext, _original=original, _rule_id=rule_id) -> RuleResult:
        result = _original(ctx)
        hits = int(result.detail.get("observed", 0))
        return make_result(_rule_id, hits > 0, RuleSeverity.INFO, RuleCategory.STRUCTURE, result.message, observed=hits)

    RULE_REGISTRY[rule_id] = positive_rule
