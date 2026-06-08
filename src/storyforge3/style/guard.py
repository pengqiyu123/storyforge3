from __future__ import annotations

from dataclasses import dataclass

from storyforge3.audit.chinese_text import count_chinese_chars, split_sentences
from storyforge3.style.contract import StyleContract


@dataclass(frozen=True)
class StyleViolation:
    rule_name: str
    observed: float | int | str
    threshold: str
    evidence: str


@dataclass(frozen=True)
class StyleGuardReport:
    contract_id: str
    passed: bool
    metrics: dict[str, float]
    violations: tuple[StyleViolation, ...]


class StyleGuard:
    def __init__(self, contract: StyleContract) -> None:
        self.contract = contract

    def check(self, text: str) -> StyleGuardReport:
        metrics = self._metrics(text)
        violations = [
            *self._range_violation("dialogue_density", metrics["dialogue_density"], self.contract.dialogue_density),
            *self._range_violation("narration_ratio", metrics["narration_ratio"], self.contract.narration_ratio),
            *self._sentence_length_violations(text),
            *self._term_violations(text),
        ]
        return StyleGuardReport(
            contract_id=self.contract.contract_id,
            passed=not violations,
            metrics=metrics,
            violations=tuple(violations),
        )

    @staticmethod
    def _metrics(text: str) -> dict[str, float]:
        sentences = split_sentences(text)
        sentence_count = max(len(sentences), 1)
        dialogue_sentences = sum(1 for sentence in sentences if "“" in sentence or "”" in sentence or '"' in sentence)
        narration_sentences = sentence_count - dialogue_sentences
        return {
            "dialogue_density": round(dialogue_sentences / sentence_count, 4),
            "narration_ratio": round(narration_sentences / sentence_count, 4),
            "avg_sentence_length": round(count_chinese_chars(text) / sentence_count, 4),
        }

    @staticmethod
    def _range_violation(rule_name: str, value: float, target: tuple[float, float]) -> list[StyleViolation]:
        minimum, maximum = target
        if minimum <= value <= maximum:
            return []
        return [
            StyleViolation(
                rule_name=rule_name,
                observed=value,
                threshold=f"{minimum}-{maximum}",
                evidence=f"{rule_name}={value}",
            )
        ]

    def _sentence_length_violations(self, text: str) -> list[StyleViolation]:
        avg = self._metrics(text)["avg_sentence_length"]
        minimum, maximum = self.contract.sentence_length_range
        if minimum <= avg <= maximum:
            return []
        return [
            StyleViolation(
                rule_name="sentence_length_range",
                observed=avg,
                threshold=f"{minimum}-{maximum}",
                evidence=f"avg_sentence_length={avg}",
            )
        ]

    def _term_violations(self, text: str) -> list[StyleViolation]:
        banned = [phrase for phrase in self.contract.banned_phrases if phrase and phrase in text]
        fatigue = [word for word in self.contract.fatigue_words if word and text.count(word) >= 3]
        violations: list[StyleViolation] = []
        if banned:
            violations.append(
                StyleViolation(
                    rule_name="banned_phrases",
                    observed="、".join(banned),
                    threshold="0 hits",
                    evidence="、".join(banned[:5]),
                )
            )
        if fatigue:
            violations.append(
                StyleViolation(
                    rule_name="fatigue_words",
                    observed="、".join(fatigue),
                    threshold="<3 hits per word",
                    evidence="、".join(fatigue[:5]),
                )
            )
        return violations
