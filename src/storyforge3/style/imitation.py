from __future__ import annotations

import math
from dataclasses import dataclass

from storyforge3.audit.chinese_text import count_chinese_chars, split_paragraphs, split_sentences

PUNCTUATION_MARKS = ("，", "。", "！", "？", "……", "；", "：")


@dataclass(frozen=True)
class StyleFingerprint:
    avg_sentence_length: float
    avg_paragraph_length: float
    dialogue_ratio: float
    short_sentence_ratio: float
    long_sentence_ratio: float
    punctuation_density: dict[str, float]
    paragraph_count_range: tuple[int, int]
    pacing_rhythm: str


@dataclass(frozen=True)
class ComplianceReport:
    sentence_length_deviation: float
    dialogue_ratio_deviation: float
    pacing_match: float
    overall_score: float
    suggestions: tuple[str, ...]


class StyleAnalyzer:
    def analyze(self, text: str) -> StyleFingerprint:
        paragraphs = split_paragraphs(text)
        sentences = split_sentences(text)
        sentence_lengths = [count_chinese_chars(sentence) for sentence in sentences if count_chinese_chars(sentence) > 0]
        paragraph_lengths = [count_chinese_chars(paragraph) for paragraph in paragraphs if count_chinese_chars(paragraph) > 0]
        sentence_count = max(len(sentence_lengths), 1)
        paragraph_count = len(paragraphs)
        avg_sentence_length = _round(sum(sentence_lengths) / sentence_count if sentence_lengths else 0.0)
        avg_paragraph_length = _round(sum(paragraph_lengths) / max(len(paragraph_lengths), 1) if paragraph_lengths else 0.0)
        total_chars = max(count_chinese_chars(text), 1)
        dialogue_chars = _dialogue_chars(text)
        short_count = sum(1 for length in sentence_lengths if length < 10)
        long_count = sum(1 for length in sentence_lengths if length > 50)
        return StyleFingerprint(
            avg_sentence_length=avg_sentence_length,
            avg_paragraph_length=avg_paragraph_length,
            dialogue_ratio=_round(dialogue_chars / total_chars),
            short_sentence_ratio=_round(short_count / sentence_count),
            long_sentence_ratio=_round(long_count / sentence_count),
            punctuation_density=_punctuation_density(text, total_chars),
            paragraph_count_range=(paragraph_count, paragraph_count),
            pacing_rhythm=_pacing_rhythm(sentence_lengths),
        )


class StyleImitator:
    def __init__(self, llm_service) -> None:
        self.llm_service = llm_service
        self.analyzer = StyleAnalyzer()

    def extract_fingerprint_from_samples(self, samples: list[str]) -> StyleFingerprint:
        fingerprints = [self.analyzer.analyze(sample) for sample in samples if sample.strip()]
        if not fingerprints:
            return self.analyzer.analyze("")
        return StyleFingerprint(
            avg_sentence_length=_round(_average(item.avg_sentence_length for item in fingerprints)),
            avg_paragraph_length=_round(_average(item.avg_paragraph_length for item in fingerprints)),
            dialogue_ratio=_round(_average(item.dialogue_ratio for item in fingerprints)),
            short_sentence_ratio=_round(_average(item.short_sentence_ratio for item in fingerprints)),
            long_sentence_ratio=_round(_average(item.long_sentence_ratio for item in fingerprints)),
            punctuation_density={
                mark: _round(_average(item.punctuation_density.get(mark, 0.0) for item in fingerprints))
                for mark in PUNCTUATION_MARKS
            },
            paragraph_count_range=(
                min(item.paragraph_count_range[0] for item in fingerprints),
                max(item.paragraph_count_range[1] for item in fingerprints),
            ),
            pacing_rhythm=_majority(item.pacing_rhythm for item in fingerprints),
        )

    def fingerprint_to_prompt(self, fingerprint: StyleFingerprint, reference_samples: list[str]) -> str:
        snippets = [sample.strip().replace("\n", " ")[:120] for sample in reference_samples if sample.strip()]
        parts = [
            "风格模仿指南：",
            f"- 平均句长：约 {fingerprint.avg_sentence_length:.1f} 个中文字符",
            f"- 平均段落长度：约 {fingerprint.avg_paragraph_length:.1f} 个中文字符",
            f"- 对话占比：约 {fingerprint.dialogue_ratio:.1%}",
            f"- 短句占比：约 {fingerprint.short_sentence_ratio:.1%}",
            f"- 长句占比：约 {fingerprint.long_sentence_ratio:.1%}",
            f"- 段落数范围：{fingerprint.paragraph_count_range[0]}-{fingerprint.paragraph_count_range[1]} 段",
            f"- 节奏：{fingerprint.pacing_rhythm}",
            "- 标点密度：" + "，".join(f"{mark}={density:.1f}/千字" for mark, density in fingerprint.punctuation_density.items()),
            "- 不要复述参考文本，不要借用原句，只模仿句长、节奏、段落和对话比例。",
        ]
        if snippets:
            parts.append("- 参考片段：" + " / ".join(snippets[:2]))
        return "\n".join(parts)

    def compare(self, fingerprint_a: StyleFingerprint, fingerprint_b: StyleFingerprint) -> float:
        scores = [
            _closeness(fingerprint_a.avg_sentence_length, fingerprint_b.avg_sentence_length),
            _closeness(fingerprint_a.avg_paragraph_length, fingerprint_b.avg_paragraph_length),
            _closeness(fingerprint_a.dialogue_ratio, fingerprint_b.dialogue_ratio),
            _closeness(fingerprint_a.short_sentence_ratio, fingerprint_b.short_sentence_ratio),
            _closeness(fingerprint_a.long_sentence_ratio, fingerprint_b.long_sentence_ratio),
            1.0 if fingerprint_a.pacing_rhythm == fingerprint_b.pacing_rhythm else 0.0,
            _punctuation_similarity(fingerprint_a, fingerprint_b),
        ]
        return _round(sum(scores) / len(scores))

    def track_compliance(self, chapter_text: str, target_fingerprint: StyleFingerprint) -> ComplianceReport:
        observed = self.analyzer.analyze(chapter_text)
        sentence_deviation = _percent_deviation(observed.avg_sentence_length, target_fingerprint.avg_sentence_length)
        dialogue_deviation = _percent_deviation(observed.dialogue_ratio, target_fingerprint.dialogue_ratio)
        pacing_match = 1.0 if observed.pacing_rhythm == target_fingerprint.pacing_rhythm else 0.0
        overall = self.compare(observed, target_fingerprint)
        suggestions = _suggestions(sentence_deviation, dialogue_deviation, pacing_match)
        return ComplianceReport(
            sentence_length_deviation=sentence_deviation,
            dialogue_ratio_deviation=dialogue_deviation,
            pacing_match=pacing_match,
            overall_score=overall,
            suggestions=tuple(suggestions),
        )


def fingerprint_from_dict(data: object) -> StyleFingerprint | None:
    if not isinstance(data, dict):
        return None
    try:
        punctuation = data.get("punctuation_density")
        return StyleFingerprint(
            avg_sentence_length=float(data["avg_sentence_length"]),
            avg_paragraph_length=float(data["avg_paragraph_length"]),
            dialogue_ratio=float(data["dialogue_ratio"]),
            short_sentence_ratio=float(data["short_sentence_ratio"]),
            long_sentence_ratio=float(data["long_sentence_ratio"]),
            punctuation_density={mark: float((punctuation or {}).get(mark, 0.0)) for mark in PUNCTUATION_MARKS},
            paragraph_count_range=tuple(data["paragraph_count_range"]),  # type: ignore[arg-type]
            pacing_rhythm=str(data["pacing_rhythm"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _dialogue_chars(text: str) -> int:
    total = 0
    in_dialogue = False
    for char in text:
        if char in {"“", '"'}:
            in_dialogue = True
            continue
        if char in {"”", '"'}:
            in_dialogue = False
            continue
        if in_dialogue and "\u4e00" <= char <= "\u9fff":
            total += 1
    return total


def _punctuation_density(text: str, total_chars: int) -> dict[str, float]:
    return {mark: _round(text.count(mark) * 1000 / total_chars) for mark in PUNCTUATION_MARKS}


def _pacing_rhythm(sentence_lengths: list[int]) -> str:
    if not sentence_lengths:
        return "medium"
    avg = sum(sentence_lengths) / len(sentence_lengths)
    if len(sentence_lengths) > 1:
        variance = sum((length - avg) ** 2 for length in sentence_lengths) / len(sentence_lengths)
        coefficient = math.sqrt(variance) / max(avg, 1)
    else:
        coefficient = 0.0
    short_ratio = sum(1 for length in sentence_lengths if length < 10) / len(sentence_lengths)
    long_ratio = sum(1 for length in sentence_lengths if length > 50) / len(sentence_lengths)
    if avg <= 18 or short_ratio >= 0.35 or coefficient >= 0.65:
        return "fast"
    if avg >= 35 and coefficient < 0.45 or long_ratio >= 0.35:
        return "slow"
    return "medium"


def _average(values) -> float:
    items = list(values)
    return sum(items) / max(len(items), 1)


def _majority(values) -> str:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return max(counts, key=counts.get) if counts else "medium"


def _closeness(a: float, b: float) -> float:
    baseline = max(abs(a), abs(b), 1.0)
    return max(0.0, 1.0 - abs(a - b) / baseline)


def _punctuation_similarity(a: StyleFingerprint, b: StyleFingerprint) -> float:
    return _round(_average(_closeness(a.punctuation_density.get(mark, 0.0), b.punctuation_density.get(mark, 0.0)) for mark in PUNCTUATION_MARKS))


def _percent_deviation(observed: float, target: float) -> float:
    return _round(abs(observed - target) / max(abs(target), 0.01))


def _suggestions(sentence_deviation: float, dialogue_deviation: float, pacing_match: float) -> list[str]:
    suggestions: list[str] = []
    if sentence_deviation > 0.25:
        suggestions.append("调整平均句长，使叙述节奏更接近目标样本。")
    if dialogue_deviation > 0.25:
        suggestions.append("调整对话与叙述比例。")
    if pacing_match < 1.0:
        suggestions.append("调整长短句交替频率，贴近目标节奏。")
    return suggestions


def _round(value: float) -> float:
    return round(value, 4)
