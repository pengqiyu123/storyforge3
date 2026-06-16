from __future__ import annotations

import pytest

from storyforge3.models import ChapterStatus
from storyforge3.state.machine import ChapterStateMachine, InvalidTransitionError


def test_current_status_defaults_to_empty(tmp_path) -> None:
    machine = ChapterStateMachine(tmp_path / "state.json")
    assert machine.current_status("book", 1) == ChapterStatus.EMPTY


def test_valid_transition_is_recorded(tmp_path) -> None:
    machine = ChapterStateMachine(tmp_path / "state.json")
    machine.advance("book", 1, ChapterStatus.PLANNED)
    assert machine.current_status("book", 1) == ChapterStatus.PLANNED
    assert machine.history("book", 1)[0]["to"] == "planned"


def test_invalid_transition_is_rejected(tmp_path) -> None:
    machine = ChapterStateMachine(tmp_path / "state.json")
    with pytest.raises(InvalidTransitionError):
        machine.advance("book", 1, ChapterStatus.EXPORTED)


def test_approved_requires_audited_state(tmp_path) -> None:
    machine = ChapterStateMachine(tmp_path / "state.json")
    machine.advance("book", 1, ChapterStatus.PLANNED)
    machine.advance("book", 1, ChapterStatus.DRAFTED)
    with pytest.raises(InvalidTransitionError):
        machine.advance("book", 1, ChapterStatus.APPROVED)


def test_truth_committed_sits_between_approved_and_exported(tmp_path) -> None:
    machine = ChapterStateMachine(tmp_path / "state.json")
    machine.advance("book", 1, ChapterStatus.PLANNED)
    machine.advance("book", 1, ChapterStatus.DRAFTED)
    machine.advance("book", 1, ChapterStatus.AUDITED)
    machine.advance("book", 1, ChapterStatus.APPROVED)

    with pytest.raises(InvalidTransitionError):
        machine.advance("book", 1, ChapterStatus.EXPORTED)

    machine.advance("book", 1, ChapterStatus.TRUTH_COMMITTED)
    machine.advance("book", 1, ChapterStatus.EXPORTED)

    assert machine.current_status("book", 1) == ChapterStatus.EXPORTED


def test_exported_can_be_unexported_to_approved(tmp_path) -> None:
    machine = ChapterStateMachine(tmp_path / "state.json")
    for status in (
        ChapterStatus.PLANNED,
        ChapterStatus.DRAFTED,
        ChapterStatus.AUDITED,
        ChapterStatus.APPROVED,
        ChapterStatus.TRUTH_COMMITTED,
        ChapterStatus.EXPORTED,
    ):
        machine.advance("book", 1, status)

    machine.advance("book", 1, ChapterStatus.APPROVED)

    assert machine.current_status("book", 1) == ChapterStatus.APPROVED
    assert machine.history("book", 1)[-1]["from"] == "exported"
    assert machine.history("book", 1)[-1]["to"] == "approved"


@pytest.mark.parametrize(
    "start_status",
    [
        ChapterStatus.NEEDS_REVIEW,
        ChapterStatus.DRAFTED,
        ChapterStatus.AUDITED,
        ChapterStatus.APPROVED,
        ChapterStatus.TRUTH_COMMITTED,
        ChapterStatus.EXPORTED,
    ],
)
def test_reaudit_states_can_transition_to_audited_or_needs_revision(tmp_path, start_status: ChapterStatus) -> None:
    machine = ChapterStateMachine(tmp_path / f"{start_status.value}.json")
    _seed_status(machine, start_status)

    if start_status in (ChapterStatus.TRUTH_COMMITTED, ChapterStatus.EXPORTED):
        machine.advance("book", 1, ChapterStatus.APPROVED)
    machine.advance("book", 1, ChapterStatus.AUDITED)

    assert machine.current_status("book", 1) == ChapterStatus.AUDITED

    machine = ChapterStateMachine(tmp_path / f"{start_status.value}-fail.json")
    _seed_status(machine, start_status)
    if start_status in (ChapterStatus.TRUTH_COMMITTED, ChapterStatus.EXPORTED):
        machine.advance("book", 1, ChapterStatus.APPROVED)
    machine.advance("book", 1, ChapterStatus.NEEDS_REVISION)

    assert machine.current_status("book", 1) == ChapterStatus.NEEDS_REVISION


def _seed_status(machine: ChapterStateMachine, status: ChapterStatus) -> None:
    path = {
        ChapterStatus.PLANNED: (ChapterStatus.PLANNED,),
        ChapterStatus.DRAFTED: (ChapterStatus.PLANNED, ChapterStatus.DRAFTED),
        ChapterStatus.AUDITED: (ChapterStatus.PLANNED, ChapterStatus.DRAFTED, ChapterStatus.AUDITED),
        ChapterStatus.APPROVED: (ChapterStatus.PLANNED, ChapterStatus.DRAFTED, ChapterStatus.AUDITED, ChapterStatus.APPROVED),
        ChapterStatus.TRUTH_COMMITTED: (
            ChapterStatus.PLANNED,
            ChapterStatus.DRAFTED,
            ChapterStatus.AUDITED,
            ChapterStatus.APPROVED,
            ChapterStatus.TRUTH_COMMITTED,
        ),
        ChapterStatus.EXPORTED: (
            ChapterStatus.PLANNED,
            ChapterStatus.DRAFTED,
            ChapterStatus.AUDITED,
            ChapterStatus.APPROVED,
            ChapterStatus.TRUTH_COMMITTED,
            ChapterStatus.EXPORTED,
        ),
        ChapterStatus.NEEDS_REVIEW: (ChapterStatus.PLANNED, ChapterStatus.NEEDS_REVIEW),
    }[status]
    for next_status in path:
        machine.advance("book", 1, next_status)
