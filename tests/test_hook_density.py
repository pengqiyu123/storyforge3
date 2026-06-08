from __future__ import annotations

from storyforge3.audit.hook_density import HookDensityAnalyzer, HookDensityReport, OverdueHook


def test_hook_density_counts_new_and_resolved_hooks() -> None:
    ledger = [
        {"hook_id": "h1", "label": "副楼异常", "introduced_in": 3, "status": "open"},
        {"hook_id": "h2", "label": "号码纸", "introduced_in": 8, "resolved_in": 8, "status": "resolved"},
        {"hook_id": "h3", "label": "新提示音", "introduced_in": 8, "status": "open"},
    ]
    report = HookDensityAnalyzer().analyze("下一秒，电子屏又亮了一次。", ledger, chapter_no=8)
    assert report == HookDensityReport(
        new_hooks=2,
        resolved_hooks=1,
        net_pressure=1,
        density_score=1.25,
        overdue_list=(),
        warning_level="healthy",
    )


def test_hook_density_flags_warning_overdue_after_10_chapters() -> None:
    ledger = [{"hook_id": "h1", "label": "旧伏笔", "introduced_in": 1, "status": "open"}]
    report = HookDensityAnalyzer().analyze("", ledger, chapter_no=12)
    assert report.warning_level == "watch"
    assert report.overdue_list == (OverdueHook("h1", "旧伏笔", 1, 1, "warning"),)


def test_hook_density_flags_critical_after_20_chapters() -> None:
    ledger = [{"hook_id": "h1", "label": "旧伏笔", "introduced_in": 1, "status": "open"}]
    report = HookDensityAnalyzer().analyze("", ledger, chapter_no=22)
    assert report.warning_level == "critical"
    assert report.overdue_list[0].level == "critical"
    assert report.overdue_list[0].chapters_overdue == 11


def test_hook_density_normalizes_dict_ledger() -> None:
    ledger = {"hooks": [{"hook_id": "h1", "label": "线索", "introduced_in": 2, "resolved_in": 4, "status": "resolved"}]}
    report = HookDensityAnalyzer().analyze("", ledger, chapter_no=4)
    assert report.resolved_hooks == 1
    assert report.net_pressure == -1


def test_hook_density_ignores_invalid_hook_entries() -> None:
    report = HookDensityAnalyzer().analyze("", [{"bad": object()}, "not-a-hook"], chapter_no=4)
    assert report.new_hooks == 0
    assert report.overdue_list == ()
