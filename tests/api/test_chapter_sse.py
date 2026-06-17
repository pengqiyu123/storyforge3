from __future__ import annotations

import json
from collections.abc import Callable
from unittest.mock import AsyncMock

import pytest

from storyforge3.api.sse import sse_manager
from storyforge3.models import ChapterResult, ChapterStatus
from storyforge3.state.machine import InvalidTransitionError


def _events(book_id: str, chapter_no: int) -> list[dict]:
    return [
        json.loads(raw)
        for raw in sse_manager._recent
        if json.loads(raw).get("book_id") == book_id and json.loads(raw).get("chapter_no") == chapter_no
    ]


def _assert_success_events(book_id: str, chapter_no: int, stage: str) -> None:
    events = _events(book_id, chapter_no)
    assert [event["type"] for event in events] == ["pipeline:start", "pipeline:complete"]
    assert [event["stage"] for event in events] == [stage, stage]


def _assert_failure_events(book_id: str, chapter_no: int, stage: str) -> None:
    events = _events(book_id, chapter_no)
    assert [event["type"] for event in events] == ["pipeline:start", "pipeline:error"]
    assert [event["stage"] for event in events] == [stage, stage]
    assert events[-1]["message"]


def _clear_events() -> None:
    sse_manager._recent.clear()


def _drafted(book_id: str, chapter_no: int) -> ChapterResult:
    return ChapterResult(book_id, chapter_no, ChapterStatus.DRAFTED, f"第{chapter_no}章", "正文")


def _audited(book_id: str, chapter_no: int) -> ChapterResult:
    return ChapterResult(book_id, chapter_no, ChapterStatus.AUDITED, f"第{chapter_no}章", "正文")


def _truth_committed(book_id: str, chapter_no: int) -> ChapterResult:
    return ChapterResult(book_id, chapter_no, ChapterStatus.TRUTH_COMMITTED, f"第{chapter_no}章", "正文")


@pytest.mark.parametrize(
    ("endpoint", "stage", "setup", "payload"),
    [
        ("plan", "plan", lambda service, book_id, chapter_no: None, None),
        ("re-plan", "plan", lambda service, book_id, chapter_no: setattr(service, "status_result", _drafted(book_id, chapter_no)), None),
        ("audit", "audit", lambda service, book_id, chapter_no: setattr(service, "status_result", _drafted(book_id, chapter_no)), None),
        ("re-audit", "audit", lambda service, book_id, chapter_no: setattr(service, "status_result", _drafted(book_id, chapter_no)), None),
        ("llm-audit", "audit", lambda service, book_id, chapter_no: None, {"text": "测试正文"}),
        ("normalize", "normalize", lambda service, book_id, chapter_no: None, {"text": "测试正文", "target_chars": 1200}),
        ("approve", "approve", lambda service, book_id, chapter_no: setattr(service, "status_result", _audited(book_id, chapter_no)), None),
        ("export", "export", lambda service, book_id, chapter_no: setattr(service, "status_result", _truth_committed(book_id, chapter_no)), {"fmt": "md"}),
    ],
)
def test_single_chapter_endpoint_emits_pipeline_start_and_complete(
    client,
    mock_chapter_service,
    endpoint: str,
    stage: str,
    setup: Callable,
    payload: dict | None,
) -> None:
    book_id = f"sse-success-{endpoint}"
    chapter_no = 7
    setup(mock_chapter_service, book_id, chapter_no)
    _clear_events()

    response = client.post(f"/api/books/{book_id}/chapters/{chapter_no}/{endpoint}", json=payload) if payload is not None else client.post(
        f"/api/books/{book_id}/chapters/{chapter_no}/{endpoint}"
    )

    assert response.status_code == 200
    _assert_success_events(book_id, chapter_no, stage)


@pytest.mark.parametrize(
    ("endpoint", "stage", "setup", "payload", "expected_status", "expected_exception"),
    [
        (
            "plan",
            "plan",
            lambda service, book_id, chapter_no: setattr(service, "raise_run_transition", True),
            None,
            None,
            InvalidTransitionError,
        ),
        (
            "re-plan",
            "plan",
            lambda service, book_id, chapter_no: (
                setattr(service, "status_result", _drafted(book_id, chapter_no)),
                setattr(service, "re_plan", AsyncMock(side_effect=ValueError("re-plan failed"))),
            ),
            None,
            409,
            None,
        ),
        (
            "audit",
            "audit",
            lambda service, book_id, chapter_no: (
                setattr(service, "status_result", _drafted(book_id, chapter_no)),
                setattr(service, "raise_audit_not_found", True),
            ),
            None,
            404,
            None,
        ),
        (
            "re-audit",
            "audit",
            lambda service, book_id, chapter_no: (
                setattr(service, "status_result", _drafted(book_id, chapter_no)),
                setattr(service, "re_audit", AsyncMock(side_effect=ValueError("re-audit failed"))),
            ),
            None,
            409,
            None,
        ),
        (
            "llm-audit",
            "audit",
            lambda service, book_id, chapter_no: setattr(
                service, "run_llm_audit", AsyncMock(side_effect=RuntimeError("llm-audit failed"))
            ),
            {"text": "测试正文"},
            None,
            RuntimeError,
        ),
        (
            "normalize",
            "normalize",
            lambda service, book_id, chapter_no: None,
            {"text": "测试正文", "target_chars": 0},
            400,
            None,
        ),
        (
            "approve",
            "approve",
            lambda service, book_id, chapter_no: (
                setattr(service, "status_result", _audited(book_id, chapter_no)),
                setattr(service, "approve", AsyncMock(side_effect=RuntimeError("approve failed"))),
            ),
            None,
            None,
            RuntimeError,
        ),
        (
            "export",
            "export",
            lambda service, book_id, chapter_no: (
                setattr(service, "status_result", _truth_committed(book_id, chapter_no)),
                setattr(service, "export", AsyncMock(side_effect=ValueError("export failed"))),
            ),
            {"fmt": "md"},
            409,
            None,
        ),
    ],
)
def test_single_chapter_endpoint_emits_pipeline_start_and_error(
    client,
    mock_chapter_service,
    endpoint: str,
    stage: str,
    setup: Callable,
    payload: dict | None,
    expected_status: int | None,
    expected_exception: type[Exception] | None,
) -> None:
    book_id = f"sse-failure-{endpoint}"
    chapter_no = 8
    setup(mock_chapter_service, book_id, chapter_no)
    _clear_events()

    def request():
        if payload is not None:
            return client.post(f"/api/books/{book_id}/chapters/{chapter_no}/{endpoint}", json=payload)
        return client.post(f"/api/books/{book_id}/chapters/{chapter_no}/{endpoint}")

    if expected_exception is not None:
        with pytest.raises(expected_exception):
            request()
    else:
        response = request()
        assert response.status_code == expected_status

    _assert_failure_events(book_id, chapter_no, stage)
