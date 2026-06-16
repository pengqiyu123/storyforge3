from __future__ import annotations

import pytest

from storyforge3.models import ChapterStatus, RunStatus
from storyforge3.state.gating import allowed_actions


@pytest.mark.parametrize(
    ("chapter_status", "run_status", "audit_blocking", "truth_exists", "expected"),
    [
        (ChapterStatus.EMPTY, RunStatus.RUNNING, 0, False, frozenset()),
        (ChapterStatus.AUDITED, RunStatus.WAITING_FOR_HUMAN, 0, False, frozenset()),
        (ChapterStatus.EMPTY, None, 0, False, frozenset({"plan"})),
        (ChapterStatus.PLANNED, None, 0, False, frozenset({"draft", "plan", "re-plan"})),
        (ChapterStatus.DRAFTED, None, 0, False, frozenset({"audit", "re-audit", "re-plan"})),
        (ChapterStatus.AUDITED, None, 0, False, frozenset({"approve", "re-audit", "revise"})),
        (ChapterStatus.AUDITED, None, 2, False, frozenset({"re-audit", "revise"})),
        (ChapterStatus.REVISED, None, 0, False, frozenset({"audit", "re-audit", "re-plan"})),
        (ChapterStatus.APPROVED, None, 0, False, frozenset({"re-audit", "truth"})),
        (ChapterStatus.APPROVED, None, 0, True, frozenset({"re-audit", "truth", "export"})),
        (ChapterStatus.TRUTH_COMMITTED, None, 0, True, frozenset({"export", "re-audit"})),
        (ChapterStatus.EXPORTED, None, 0, True, frozenset({"re-audit", "unexport"})),
        (ChapterStatus.NEEDS_REVIEW, None, 0, False, frozenset({"plan", "draft", "audit", "re-audit", "re-plan"})),
        (ChapterStatus.NEEDS_REVIEW, RunStatus.RUNNING, 0, False, frozenset()),
        (ChapterStatus.NEEDS_REVISION, None, 0, False, frozenset({"revise", "re-audit", "re-plan"})),
    ],
)
def test_allowed_actions_matches_backend_gate_table(
    chapter_status: ChapterStatus,
    run_status: RunStatus | None,
    audit_blocking: int,
    truth_exists: bool,
    expected: frozenset[str],
) -> None:
    assert allowed_actions(chapter_status, run_status, audit_blocking, truth_exists) == expected


def test_allowed_actions_export_compat_for_approved_with_truth() -> None:
    assert allowed_actions(ChapterStatus.APPROVED, None, 0, True) == frozenset({"truth", "export", "re-audit"})


@pytest.mark.parametrize(
    ("resume_from", "expected"),
    [
        ("truth", ["truth", "export"]),
        ("plan", ["plan", "draft", "audit", "revise", "approve", "truth", "export"]),
        (None, ["plan", "draft", "audit", "revise", "approve", "truth", "export"]),
        ("nonexistent", ["plan", "draft", "audit", "revise", "approve", "truth", "export"]),
    ],
)
def test_stages_from_resumes_inclusively(resume_from: str | None, expected: list[str]) -> None:
    from storyforge3.api.routes.chapters import _stages_from

    full_stages = ["plan", "draft", "audit", "revise", "approve", "truth", "export"]

    assert _stages_from(resume_from, full_stages) == expected
