from __future__ import annotations

from storyforge3.audit.runner import AuditRunner
from storyforge3.models import RuleSeverity
from storyforge3.style.contract import DEFAULT_STYLE_CONTRACT, StyleContract
from storyforge3.style.guard import StyleGuard


def test_style_guard_passes_balanced_text() -> None:
    text = (
        "林默看向门口，先把脚步停在电子屏外侧，等那串提示音彻底消失。"
        "走廊里的灯光有些冷，照得地面像刚擦过一样发亮。"
        "“先别进来。”护士压低声音。"
        "他点点头，没有追问，只把号码纸折进掌心。"
    )
    report = StyleGuard(DEFAULT_STYLE_CONTRACT).check(text)
    assert report.passed is True
    assert report.violations == ()


def test_style_guard_detects_banned_phrase() -> None:
    report = StyleGuard(DEFAULT_STYLE_CONTRACT).check("本章必须说明核心剧情。林默突然明白。")
    assert report.passed is False
    assert any(item.rule_name == "banned_phrases" for item in report.violations)


def test_style_guard_detects_dialogue_density_low() -> None:
    contract = StyleContract(contract_id="dialogue", display_name="Dialogue", dialogue_density=(0.5, 0.8))
    report = StyleGuard(contract).check("林默走进房间。他坐下。他看向窗外。")
    assert any(item.rule_name == "dialogue_density" for item in report.violations)


def test_style_guard_detects_sentence_length_out_of_range() -> None:
    contract = StyleContract(contract_id="short", display_name="Short", sentence_length_range=(2, 5))
    report = StyleGuard(contract).check("林默站在副楼门口听见走廊尽头传来一串非常短促的提示音。")
    assert any(item.rule_name == "sentence_length_range" for item in report.violations)


def test_audit_runner_adds_style_contract_report_only_result(sample_chapter_text: str) -> None:
    contract = StyleContract(contract_id="strict", display_name="Strict", banned_phrases=("林默",))
    audit = AuditRunner(style_contract=contract).run_audit(1, sample_chapter_text)
    result = next(item for item in audit.rule_results if item.rule_id == "style_contract_check")
    assert result.severity == RuleSeverity.INFO
    assert result.passed is False
    assert audit.passed is True
