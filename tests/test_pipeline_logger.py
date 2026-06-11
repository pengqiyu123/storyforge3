from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from storyforge3.logging.pipeline_logger import PipelineLogger, PipelineRunRecord
from storyforge3.models import ChapterStatus, LLMCallRecord
from storyforge3.workflow import ChapterWorkflow

from tests.test_workflow import MockClient, valid_chapter_text


def run(coro):
    return asyncio.run(coro)


def record(book_id: str = "lurenjia", chapter_no: int = 8, task: str = "draft", status: str = "success") -> PipelineRunRecord:
    return PipelineRunRecord(
        book_id=book_id,
        chapter_no=chapter_no,
        task=task,
        timestamp="2026-06-08T00:00:00+00:00",
        status=status,
    )


class RecordingMockClient(MockClient):
    def __init__(self, draft: str, truth_payload: dict | None = None, fail_truth: bool = False, normalized: str | None = None) -> None:
        super().__init__(draft, truth_payload=truth_payload, fail_truth=fail_truth, normalized=normalized)
        self.last_call: LLMCallRecord | None = None

    async def generate_text(self, task_name, system_prompt, user_payload, **kwargs):
        self.last_call = LLMCallRecord(
            task_name=task_name,
            model="test-model",
            prompt_version=str(kwargs.get("prompt_version") or "unknown"),
            input_tokens=10,
            output_tokens=20,
            latency_ms=1.0,
            success=True,
        )
        return await super().generate_text(task_name, system_prompt, user_payload, **kwargs)

    async def generate_json(self, task_name, system_prompt, user_payload, response_schema, **kwargs):
        self.last_call = LLMCallRecord(
            task_name=task_name,
            model="test-model",
            prompt_version=str(kwargs.get("prompt_version") or "unknown"),
            input_tokens=5,
            output_tokens=5,
            latency_ms=1.0,
            success=not self.fail_truth,
            error="truth failed" if self.fail_truth else None,
        )
        return await super().generate_json(task_name, system_prompt, user_payload, response_schema, **kwargs)


def test_append_creates_jsonl(tmp_path: Path) -> None:
    logger = PipelineLogger(tmp_path)

    path = logger.append(record())

    assert path == tmp_path / "lurenjia" / "runs" / "pipeline.jsonl"
    data = json.loads(path.read_text(encoding="utf-8").strip())
    assert data["book_id"] == "lurenjia"
    assert data["task"] == "draft"
    assert data["status"] == "success"


def test_append_multiple_records(tmp_path: Path) -> None:
    logger = PipelineLogger(tmp_path)

    logger.append(record(task="plan"))
    logger.append(record(task="draft"))

    lines = (tmp_path / "lurenjia" / "runs" / "pipeline.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["task"] for line in lines] == ["plan", "draft"]


def test_read_records_returns_most_recent(tmp_path: Path) -> None:
    logger = PipelineLogger(tmp_path)
    for index in range(5):
        logger.append(record(task=f"task-{index}"))

    records = logger.read_records("lurenjia", limit=3)

    assert [item.task for item in records] == ["task-2", "task-3", "task-4"]


def test_read_records_empty_file(tmp_path: Path) -> None:
    assert PipelineLogger(tmp_path).read_records("missing") == []


def test_record_serialization_roundtrip() -> None:
    original = PipelineRunRecord(
        book_id="lurenjia",
        chapter_no=8,
        task="audit",
        timestamp="2026-06-08T00:00:00+00:00",
        status="success",
        audit_passed=False,
        audit_blocking=1,
        audit_warnings=2,
        llm_calls=[{"task_name": "draft", "success": True}],
    )

    restored = PipelineRunRecord(**json.loads(json.dumps(asdict(original), ensure_ascii=False)))

    assert restored == original


def test_malformed_line_skipped(tmp_path: Path) -> None:
    logger = PipelineLogger(tmp_path)
    path = tmp_path / "lurenjia" / "runs" / "pipeline.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("not-json\n" + json.dumps(asdict(record(task="audit")), ensure_ascii=False) + "\n", encoding="utf-8")

    records = logger.read_records("lurenjia")

    assert [item.task for item in records] == ["audit"]


def test_workflow_logs_on_draft_success(config, book_workspace: Path) -> None:
    logger = PipelineLogger(config.books_dir)
    workflow = ChapterWorkflow(config, client=RecordingMockClient(valid_chapter_text(1000)), logger=logger)

    result = run(workflow.run("lurenjia", 8, human_confirm=lambda _: True))

    assert result.status == ChapterStatus.EXPORTED
    records = logger.read_records("lurenjia")
    tasks = [item.task for item in records]
    assert "draft" in tasks
    draft = next(item for item in records if item.task == "draft")
    assert draft.status == "success"
    assert draft.status_before == "planned"
    assert draft.status_after == "drafted"
    assert draft.llm_calls


def test_workflow_logs_on_audit_with_details(config, book_workspace: Path) -> None:
    logger = PipelineLogger(config.books_dir)
    workflow = ChapterWorkflow(config, client=RecordingMockClient("短稿"), logger=logger)

    result = run(workflow.run("lurenjia", 8, human_confirm=lambda _: True))

    assert result.status == ChapterStatus.NEEDS_REVIEW
    audit = next(item for item in logger.read_records("lurenjia") if item.task == "audit")
    assert audit.status == "success"
    assert audit.audit_passed is False
    assert audit.audit_blocking is not None
    assert audit.audit_blocking >= 1
    assert audit.audit_warnings is not None


class FailingLogger(PipelineLogger):
    def append(self, record: PipelineRunRecord) -> Path:
        raise OSError("log disk unavailable")


def test_log_failure_does_not_block_pipeline(config, book_workspace: Path) -> None:
    workflow = ChapterWorkflow(config, client=RecordingMockClient(valid_chapter_text(1000)), logger=FailingLogger(config.books_dir))

    result = run(workflow.run("lurenjia", 8, human_confirm=lambda _: True))

    assert result.status == ChapterStatus.EXPORTED
