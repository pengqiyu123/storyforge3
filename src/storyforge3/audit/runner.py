from __future__ import annotations

from storyforge3.audit.context import build_mechanical_context
from storyforge3.audit.rules import RULE_REGISTRY
from storyforge3.models import AuditResult, RuleCategory, RuleResult, RuleSeverity
from storyforge3.style.contract import StyleContract


class AuditRunner:
    def __init__(self, style_contract: StyleContract | None = None) -> None:
        self.style_contract = style_contract

    def run_audit(self, chapter_no: int, text: str) -> AuditResult:
        context = build_mechanical_context(chapter_no, text)
        results = tuple(check(context) for check in RULE_REGISTRY.values())
        if self.style_contract is not None:
            results = (*results, self._style_contract_result(text))
        blocking = tuple(result.rule_id for result in results if not result.passed and result.severity == RuleSeverity.BLOCKING)
        warnings = tuple(result.rule_id for result in results if not result.passed and result.severity == RuleSeverity.WARNING)
        info = tuple(result.rule_id for result in results if not result.passed and result.severity == RuleSeverity.INFO)
        return AuditResult(
            chapter_no=chapter_no,
            passed=not blocking,
            blocking_issues=blocking,
            warnings=warnings,
            info=info,
            rule_results=results,
        )

    def _style_contract_result(self, text: str) -> RuleResult:
        from storyforge3.style.guard import StyleGuard

        report = StyleGuard(self.style_contract).check(text)
        return RuleResult(
            "style_contract_check",
            report.passed,
            RuleSeverity.INFO,
            RuleCategory.STYLE,
            "风格合约检查（report-only）",
            {
                "contract_id": report.contract_id,
                "metrics": report.metrics,
                "violations": [violation.__dict__ for violation in report.violations],
            },
        )
