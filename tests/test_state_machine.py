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
