from __future__ import annotations

from dataclasses import FrozenInstanceError

from storyforge3.style.imitation import StyleAnalyzer, StyleFingerprint, StyleImitator


SAMPLE_A = (
    "林默站在门口，先听见灯管细细地响。\n\n"
    "“你确定要进去？”许青问。\n\n"
    "他点头。走廊尽头的影子贴着墙根退了一寸，像有人把名字悄悄擦掉。"
)

SAMPLE_B = (
    "雨停了。\n\n"
    "周砚把病例夹放回抽屉，声音很轻。"
    "“不是失踪，是没人记得他来过。”\n\n"
    "林默没有立刻回答。他看着玻璃上的倒影，忽然发现自己的脸也淡了一层。"
)


def test_style_fingerprint_is_frozen() -> None:
    fingerprint = StyleAnalyzer().analyze(SAMPLE_A)
    try:
        fingerprint.avg_sentence_length = 1.0  # type: ignore[misc]
    except FrozenInstanceError:
        pass
    else:
        raise AssertionError("StyleFingerprint should be frozen")


def test_style_analyzer_extracts_chinese_text_metrics() -> None:
    fingerprint = StyleAnalyzer().analyze(SAMPLE_A)

    assert fingerprint.avg_sentence_length > 5
    assert fingerprint.avg_paragraph_length > fingerprint.avg_sentence_length
    assert 0 < fingerprint.dialogue_ratio < 1
    assert fingerprint.short_sentence_ratio > 0
    assert fingerprint.long_sentence_ratio == 0
    assert fingerprint.punctuation_density["。"] > 0
    assert fingerprint.punctuation_density["，"] > 0
    assert fingerprint.paragraph_count_range == (3, 3)
    assert fingerprint.pacing_rhythm in {"fast", "medium", "slow"}


def test_style_imitator_averages_samples_and_builds_prompt() -> None:
    imitator = StyleImitator(llm_service=None)
    fingerprint = imitator.extract_fingerprint_from_samples([SAMPLE_A, SAMPLE_B])

    assert fingerprint.paragraph_count_range == (3, 3)
    prompt = imitator.fingerprint_to_prompt(fingerprint, [SAMPLE_A, SAMPLE_B])
    assert "风格模仿指南" in prompt
    assert "平均句长" in prompt
    assert "对话占比" in prompt
    assert "不要复述参考文本" in prompt
    assert "林默站在门口" in prompt


def test_style_compare_and_compliance_report() -> None:
    imitator = StyleImitator(llm_service=None)
    target = imitator.extract_fingerprint_from_samples([SAMPLE_A, SAMPLE_B])
    similar = StyleAnalyzer().analyze(SAMPLE_A)
    different = StyleFingerprint(
        avg_sentence_length=80.0,
        avg_paragraph_length=240.0,
        dialogue_ratio=0.0,
        short_sentence_ratio=0.0,
        long_sentence_ratio=1.0,
        punctuation_density={"，": 0.0, "。": 0.0, "！": 0.0, "？": 0.0, "……": 0.0, "；": 0.0, "：": 0.0},
        paragraph_count_range=(1, 1),
        pacing_rhythm="slow",
    )

    assert imitator.compare(target, similar) > imitator.compare(target, different)
    report = imitator.track_compliance(SAMPLE_A, target)
    assert 0 <= report.overall_score <= 1
    assert report.pacing_match in {0.0, 1.0}
    assert isinstance(report.suggestions, tuple)
