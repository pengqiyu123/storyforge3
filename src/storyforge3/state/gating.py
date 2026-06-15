from __future__ import annotations

from storyforge3.models import ChapterStatus, RunStatus

_ACTIVE_RUN_STATUSES = {RunStatus.RUNNING, RunStatus.WAITING_FOR_HUMAN}


def allowed_actions(
    chapter_status: ChapterStatus,
    run_status: RunStatus | None,
    audit_blocking: int,
    truth_exists: bool,
) -> frozenset[str]:
    """Return allowed stage actions for a chapter's current durable state."""
    if run_status in _ACTIVE_RUN_STATUSES:
        return frozenset()

    if chapter_status == ChapterStatus.EMPTY:
        return frozenset({"plan"})
    if chapter_status == ChapterStatus.PLANNED:
        return frozenset({"draft", "plan"})
    if chapter_status == ChapterStatus.DRAFTED:
        return frozenset({"audit"})
    if chapter_status == ChapterStatus.AUDITED:
        return frozenset({"revise"} if audit_blocking > 0 else {"approve", "revise"})
    if chapter_status == ChapterStatus.REVISED:
        return frozenset({"audit"})
    if chapter_status == ChapterStatus.APPROVED:
        actions = {"truth"}
        if truth_exists:
            actions.add("export")
        return frozenset(actions)
    if chapter_status == ChapterStatus.TRUTH_COMMITTED:
        return frozenset({"export"})
    if chapter_status in {ChapterStatus.EXPORTED, ChapterStatus.NEEDS_REVIEW}:
        return frozenset()
    return frozenset()
