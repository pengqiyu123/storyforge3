from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from storyforge3.config import StoryForge3Config
from storyforge3.models import ChapterStatus, LLMCallRecord
from storyforge3.workflow import ChapterWorkflow


def run(coro):
    return asyncio.run(coro)


class WorkflowDiagnosticsClient:
    def __init__(self, *, draft: str, revised: str | None = None, fail_draft: bool = False) -> None:
        self.draft = draft
        self.revised = revised or draft
        self.fail_draft = fail_draft
        self.revise_calls = 0
        self.last_call: LLMCallRecord | None = None

    async def generate_text(self, task_name: str, _system_prompt: str, _user_payload: dict, **kwargs: Any) -> str:
        self.last_call = LLMCallRecord(
            task_name=task_name,
            model="test-model",
            prompt_version=str(kwargs.get("prompt_version") or "unknown"),
            input_tokens=1,
            output_tokens=1,
            latency_ms=1.0,
            success=True,
        )
        if task_name == "plan":
            return "第8章计划"
        if task_name == "draft":
            if self.fail_draft:
                raise RuntimeError("draft exploded")
            return self.draft
        return self.draft

    async def generate_json(self, task_name: str, _system_prompt: str, user_payload: dict, _response_schema: dict, **kwargs: Any) -> dict:
        self.last_call = LLMCallRecord(
            task_name=task_name,
            model="test-model",
            prompt_version=str(kwargs.get("prompt_version") or "unknown"),
            input_tokens=1,
            output_tokens=1,
            latency_ms=1.0,
            success=True,
        )
        if task_name == "revise":
            self.revise_calls += 1
            find = user_payload["patch_targets"][0]["window_text"].split("\n\n", maxsplit=1)[0]
            return {"patches": [{"find": find, "replace": f"{self.revised}{self.revise_calls}", "rule_id": "below_min_word_count"}]}
        return {
            "fact_assertions": ["林默完成检测。"],
            "character_updates": [],
            "relationship_updates": [],
            "hook_updates": [],
            "irreversible_facts": [],
            "notes": [],
        }


def valid_text(chars: int = 1000) -> str:
    hook = "门外传来异常声音。"
    return f"{hook}\n\n{'林' * (chars - len(hook))}"


def write_book_meta(root: Path, *, target_chars: int = 800) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "book.json").write_text(
        (
            "{"
            '"book_id":"lurenjia","title":"我是路人甲","genre":"urban","platform":"tomato",'
            '"status":"incubating","target_chapters":10,'
            f'"chapter_word_count":{target_chars},"language":"zh",'
            '"current_chapter":0,"created_at":"","updated_at":""'
            "}"
        ),
        encoding="utf-8",
    )
    (root / "context.md").write_text("主角林默，能力是存在感调节。", encoding="utf-8")


def diagnostics_dir(config: StoryForge3Config, book_id: str = "lurenjia") -> Path:
    return Path(config.books_dir) / book_id / "diagnostics"


def test_diagnostics_written_on_revision_exhausted(config: StoryForge3Config) -> None:
    write_book_meta(Path(config.books_dir) / "lurenjia")
    workflow = ChapterWorkflow(config, client=WorkflowDiagnosticsClient(draft="短稿", revised="仍短"))

    result = run(workflow.run("lurenjia", 1, human_confirm=lambda _: True))

    assert result.status == ChapterStatus.NEEDS_REVIEW
    assert result.error == "revision_exhausted"
    diag_dir = diagnostics_dir(config)
    assert (diag_dir / "chapter_1_last_draft.md").read_text(encoding="utf-8") == result.text
    assert (diag_dir / "chapter_1_error.txt").read_text(encoding="utf-8") == "revision_exhausted"
    audit_payload = json.loads((diag_dir / "chapter_1_audit.json").read_text(encoding="utf-8"))
    assert audit_payload["chapter_no"] == 1
    assert audit_payload["passed"] is False


def test_diagnostics_written_on_exception(config: StoryForge3Config) -> None:
    write_book_meta(Path(config.books_dir) / "lurenjia")
    workflow = ChapterWorkflow(config, client=WorkflowDiagnosticsClient(draft="", fail_draft=True))

    result = run(workflow.run("lurenjia", 1, human_confirm=lambda _: True))

    assert result.status == ChapterStatus.NEEDS_REVIEW
    assert result.error == "draft exploded"
    diag_dir = diagnostics_dir(config)
    assert (diag_dir / "chapter_1_error.txt").read_text(encoding="utf-8") == "draft exploded"
    assert not (diag_dir / "chapter_1_last_draft.md").exists()
    assert not (diag_dir / "chapter_1_audit.json").exists()


def test_no_diagnostics_on_success(config: StoryForge3Config) -> None:
    write_book_meta(Path(config.books_dir) / "lurenjia")
    workflow = ChapterWorkflow(config, client=WorkflowDiagnosticsClient(draft=valid_text()))

    result = run(workflow.run("lurenjia", 1, human_confirm=lambda _: True))

    assert result.status == ChapterStatus.EXPORTED
    diag_dir = diagnostics_dir(config)
    assert not diag_dir.exists() or not any(diag_dir.iterdir())


def test_diagnostics_audit_json_valid(config: StoryForge3Config) -> None:
    write_book_meta(Path(config.books_dir) / "lurenjia")
    workflow = ChapterWorkflow(config, client=WorkflowDiagnosticsClient(draft="短稿", revised="仍短"))

    run(workflow.run("lurenjia", 1, human_confirm=lambda _: True))

    audit_payload = json.loads((diagnostics_dir(config) / "chapter_1_audit.json").read_text(encoding="utf-8"))
    assert isinstance(audit_payload["rule_results"], list)
    assert any(result["rule_id"] == "below_min_word_count" for result in audit_payload["rule_results"])
