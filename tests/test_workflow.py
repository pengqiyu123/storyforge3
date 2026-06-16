from __future__ import annotations

import asyncio
from pathlib import Path

from storyforge3.models import ChapterStatus, LLMCallRecord
from storyforge3.truth.database import TruthDatabase, TruthEntry
from storyforge3.workflow import ChapterWorkflow


def run(coro):
    return asyncio.run(coro)


class MockClient:
    def __init__(self, draft: str, truth_payload: dict | None = None, fail_truth: bool = False, normalized: str | None = None) -> None:
        self.draft = draft
        self.normalized = normalized or draft
        self.calls: list[str] = []
        self.truth_payload = truth_payload or {
            "fact_assertions": ["林默完成第8章检测。"],
            "character_updates": [],
            "relationship_updates": [],
            "hook_updates": [],
            "irreversible_facts": [],
            "notes": [],
        }
        self.fail_truth = fail_truth

    async def generate_text(self, task_name, system_prompt, user_payload, **kwargs):
        self.calls.append(task_name)
        if task_name == "plan":
            return "第8章计划"
        if task_name == "length_normalize":
            return self.normalized
        return self.draft

    async def generate_json(self, task_name, system_prompt, user_payload, response_schema, **kwargs):
        if self.fail_truth:
            raise RuntimeError("truth failed")
        return self.truth_payload


class RevisionLoopMockClient:
    def __init__(self, draft: str, revised: str) -> None:
        self.draft = draft
        self.revised = revised
        self.calls: list[tuple[str, dict]] = []
        self.last_call: LLMCallRecord | None = None
        self.revise_json_calls = 0

    async def generate_text(self, task_name, system_prompt, user_payload, **kwargs):
        self.calls.append((task_name, user_payload))
        self.last_call = LLMCallRecord(
            task_name=task_name,
            model="test-model",
            prompt_version=str(kwargs.get("prompt_version") or "unknown"),
            input_tokens=10,
            output_tokens=20,
            latency_ms=1.0,
            success=True,
        )
        if task_name == "plan":
            return "第8章计划"
        if task_name == "draft_chunk_plan":
            return "1. 第一段\n2. 第二段"
        if task_name == "draft_chunk":
            return self.draft
        if task_name == "revise":
            return self.revised
        return self.draft

    async def generate_json(self, task_name, system_prompt, user_payload, response_schema, **kwargs):
        self.last_call = LLMCallRecord(
            task_name=task_name,
            model="test-model",
            prompt_version=str(kwargs.get("prompt_version") or "unknown"),
            input_tokens=5,
            output_tokens=5,
            latency_ms=1.0,
            success=True,
        )
        if task_name == "revise":
            self.calls.append((task_name, user_payload))
            self.revise_json_calls += 1
            window_text = user_payload["patch_targets"][0]["window_text"]
            find = self.draft if self.draft in window_text else window_text.split("\n\n", maxsplit=1)[0]
            replacement = self.revised if self.revise_json_calls == 1 else f"{self.revised}{self.revise_json_calls}"
            return {"patches": [{"find": find, "replace": replacement, "rule_id": "below_min_word_count"}]}
        return {
            "fact_assertions": ["林默完成修订后的检测。"],
            "character_updates": [],
            "relationship_updates": [],
            "hook_updates": [],
            "irreversible_facts": [],
            "notes": [],
        }


class PayloadWorkflowMockClient(RevisionLoopMockClient):
    async def generate_text(self, task_name, system_prompt, user_payload, **kwargs):
        self.calls.append((task_name, user_payload))
        self.last_call = LLMCallRecord(
            task_name=task_name,
            model="test-model",
            prompt_version=str(kwargs.get("prompt_version") or "unknown"),
            input_tokens=10,
            output_tokens=20,
            latency_ms=1.0,
            success=True,
        )
        if task_name == "plan":
            return "第8章计划"
        return self.draft


class PlanPromptWorkflowMockClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def generate_text(self, task_name, system_prompt, user_payload, **kwargs):
        self.calls.append({"task_name": task_name, "system_prompt": system_prompt, "payload": user_payload})
        return "第8章计划"


def chinese_text(chars: int) -> str:
    return "林" * chars


def valid_chapter_text(chars: int) -> str:
    hook = "门外传来异常声音。"
    return f"{hook}\n\n{'林' * (chars - 8)}"


def no_hook_chapter_text(chars: int) -> str:
    head = "林默站在旧楼前，手里攥着登记表。"
    second = "陈野坐在窗口后，低头翻着登记册。"
    third = "白色灯光落在桌面上，纸张边缘微微发亮。"
    used = sum(len(part) for part in (head, second, third))
    return f"{head}\n\n{second}\n\n{third}\n\n{'林' * (chars - used)}"


def write_book_meta(root: Path, *, target_chars: int = 1000) -> None:
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


def write_world_and_characters(root: Path) -> None:
    (root / "world.json").write_text(
        (
            "{"
            '"book_id":"lurenjia",'
            '"setting":"存在感系统影响人群注意力",'
            '"power_system":"异常等级由检测中心记录",'
            '"core_conflict":"林默必须隐藏能力又接受检测",'
            '"rules":["过度使用会留下异常痕迹"]'
            "}"
        ),
        encoding="utf-8",
    )
    (root / "characters.json").write_text(
        (
            "{"
            '"characters":['
            "{"
            '"book_id":"lurenjia",'
            '"name":"林默",'
            '"role":"protagonist",'
            '"profile":"高三学生，能力是调节自己的存在感",'
            '"personality":"谨慎但不懦弱",'
            '"abilities":["存在感调节"],'
            '"arc_direction":"从躲避检测到主动追查异常"'
            "},"
            "{"
            '"book_id":"lurenjia",'
            '"name":"许青",'
            '"role":"major",'
            '"profile":"异常检测中心实习记录员",'
            '"personality":"细心，善于观察",'
            '"abilities":[],'
            '"arc_direction":"从旁观记录到帮助林默"'
            "}"
            "]}"
        ),
        encoding="utf-8",
    )


def test_workflow_step_plan_uses_registry_plan_template(config, book_workspace: Path) -> None:
    client = PlanPromptWorkflowMockClient()
    workflow = ChapterWorkflow(config, client=client)

    plan = run(workflow.step_plan(run(workflow.step_import("lurenjia")), 8))

    assert plan == "第8章计划"
    call = client.calls[0]
    assert call["task_name"] == "plan"
    assert "钩子账" in call["system_prompt"]
    assert "### 本章目标" in call["system_prompt"]
    assert "不要输出正文" in call["system_prompt"]
    assert "只输出章节正文" not in call["system_prompt"]


def test_workflow_exports_after_human_confirm(config, book_workspace: Path, sample_chapter_text: str) -> None:
    workflow = ChapterWorkflow(config, client=MockClient(sample_chapter_text))
    result = run(workflow.run("lurenjia", 8, human_confirm=lambda _: True))
    assert result.status == ChapterStatus.EXPORTED
    assert result.truth is not None
    assert (book_workspace / "plans" / "0008.json").exists()
    assert (book_workspace / "chapters" / "0008.md").read_text(encoding="utf-8") == sample_chapter_text
    assert (book_workspace / "state" / "chapter_states.json").exists()
    assert not (book_workspace.parent / "state.json").exists()
    assert (book_workspace / "exports" / "chapter-0008.txt").exists()


def test_workflow_pauses_without_human_confirm(config, book_workspace: Path, sample_chapter_text: str) -> None:
    workflow = ChapterWorkflow(config, client=MockClient(sample_chapter_text))
    result = run(workflow.run("lurenjia", 8))
    assert result.status == ChapterStatus.NEEDS_REVIEW
    assert result.error == "human_confirmation_required"


def test_workflow_truth_failure_needs_review(config, book_workspace: Path, sample_chapter_text: str) -> None:
    workflow = ChapterWorkflow(config, client=MockClient(sample_chapter_text, fail_truth=True))
    result = run(workflow.run("lurenjia", 8, human_confirm=lambda _: True))
    assert result.status == ChapterStatus.NEEDS_REVIEW
    assert "truth" in (result.error or "")
    assert result.text == sample_chapter_text
    assert result.audit is not None


def test_workflow_requires_persisted_truth_before_export(config, book_workspace: Path, sample_chapter_text: str) -> None:
    workflow = ChapterWorkflow(config, client=MockClient(sample_chapter_text))

    def drop_truth(_book_id, _truth):
        return book_workspace / "truth" / "chapter-0008.json"

    workflow.truth_store.save = drop_truth

    result = run(workflow.run("lurenjia", 8, human_confirm=lambda _: True))

    assert result.status == ChapterStatus.NEEDS_REVIEW
    assert "Truth 提取未完成" in (result.error or "")
    assert not (book_workspace / "exports" / "chapter-0008.txt").exists()


def test_workflow_normalizes_draft_before_audit_and_export(config, book_workspace: Path) -> None:
    write_book_meta(book_workspace, target_chars=800)
    normalized_text = valid_chapter_text(1000)
    client = MockClient(chinese_text(1100), normalized=normalized_text)
    workflow = ChapterWorkflow(config, client=client)

    result = run(workflow.run("lurenjia", 8, human_confirm=lambda _: True))

    assert result.status == ChapterStatus.EXPORTED
    assert result.text == normalized_text
    assert "length_normalize" in client.calls
    exported = (book_workspace / "exports" / "chapter-0008.txt").read_text(encoding="utf-8")
    assert normalized_text in exported


def test_workflow_uses_chunked_draft_above_threshold(config, book_workspace: Path) -> None:
    write_book_meta(book_workspace, target_chars=1000)
    client = RevisionLoopMockClient(valid_chapter_text(500), valid_chapter_text(1000))
    workflow = ChapterWorkflow(config, client=client)

    text = run(workflow.step_draft("第8章计划", run(workflow.step_import("lurenjia")), 8))

    assert text == f"{valid_chapter_text(500)}\n\n{valid_chapter_text(500)}"
    assert [task_name for task_name, _ in client.calls] == ["draft_chunk_plan", "draft_chunk", "draft_chunk"]
    assert client.calls[1][1]["target_chars"] == 1000
    assert client.calls[2][1]["previous_chunk_tail"] == valid_chapter_text(500)[-200:]


def test_workflow_draft_payload_includes_world_and_character_context(config, book_workspace: Path) -> None:
    write_world_and_characters(book_workspace)
    client = PayloadWorkflowMockClient(valid_chapter_text(1000), valid_chapter_text(1000))
    workflow = ChapterWorkflow(config, client=client)

    result = run(workflow.run("lurenjia", 8, human_confirm=lambda _: True))

    assert result.status == ChapterStatus.EXPORTED
    draft_payload = client.calls[1][1]
    assert draft_payload["world"] == {
        "setting": "存在感系统影响人群注意力",
        "power_system": "异常等级由检测中心记录",
        "core_conflict": "林默必须隐藏能力又接受检测",
    }
    assert draft_payload["characters"] == (
        {"name": "林默", "role": "protagonist", "profile": "高三学生，能力是调节自己的存在感", "personality": "谨慎但不懦弱"},
        {"name": "许青", "role": "major", "profile": "异常检测中心实习记录员", "personality": "细心，善于观察"},
    )


def test_workflow_draft_payload_uses_retrieved_truth(config, book_workspace: Path) -> None:
    db = TruthDatabase(Path(config.books_dir) / "truth.db")
    db.insert_entries(
        "lurenjia",
        7,
        [
            TruthEntry(
                id=None,
                book_id="lurenjia",
                chapter_no=7,
                category="plot_point",
                content="许青发现林默的存在感残痕。",
                importance=0.9,
                related_chapters=(),
                created_at="2026-06-02T00:00:00+00:00",
            )
        ],
    )
    client = PayloadWorkflowMockClient(valid_chapter_text(1000), valid_chapter_text(1000))
    workflow = ChapterWorkflow(config, client=client)

    result = run(workflow.run("lurenjia", 8, human_confirm=lambda _: True))

    assert result.status == ChapterStatus.EXPORTED
    draft_payload = client.calls[1][1]
    assert "许青发现林默的存在感残痕。" in draft_payload["relevant_truth"]
    assert "fact_assertions" not in draft_payload["relevant_truth"]


def test_workflow_draft_payload_includes_context_source_summary(config, book_workspace: Path) -> None:
    write_world_and_characters(book_workspace)
    db = TruthDatabase(Path(config.books_dir) / "truth.db")
    db.insert_entries(
        "lurenjia",
        7,
        [
            TruthEntry(
                id=None,
                book_id="lurenjia",
                chapter_no=7,
                category="plot_point",
                content="许青发现林默的存在感残痕。",
                importance=0.9,
                related_chapters=(),
                created_at="2026-06-02T00:00:00+00:00",
            )
        ],
    )
    client = PayloadWorkflowMockClient(valid_chapter_text(1000), valid_chapter_text(1000))
    workflow = ChapterWorkflow(config, client=client)

    result = run(workflow.run("lurenjia", 8, human_confirm=lambda _: True))

    assert result.status == ChapterStatus.EXPORTED
    draft_payload = client.calls[1][1]
    sources = {item["source"]: item for item in draft_payload["context_sources"]}
    assert "chapter_goal" in sources
    assert "previous_chapter_tail" in sources
    assert "book_context" in sources
    assert "world_rules" in sources
    assert "character_profiles" in sources
    assert "truth_retrieval" in sources
    assert sources["chapter_goal"]["priority"] == "CRITICAL"
    assert sources["truth_retrieval"]["priority"] == "HIGH"
    assert "[chapter_goal]\n第8章计划" in draft_payload["context_prompt"]


def test_workflow_revises_and_reaudits_blocking_audit_before_export(config, book_workspace: Path) -> None:
    client = RevisionLoopMockClient("短稿", valid_chapter_text(1000))
    workflow = ChapterWorkflow(config, client=client)

    result = run(workflow.run("lurenjia", 8, human_confirm=lambda _: True))

    assert result.status == ChapterStatus.EXPORTED
    assert result.audit is not None
    assert result.audit.passed is True
    assert result.text == valid_chapter_text(1000)
    assert [task_name for task_name, _ in client.calls] == ["plan", "draft", "revise"]
    revise_payload = client.calls[-1][1]
    assert revise_payload["mode"] == "surgical"
    assert "below_min_word_count" in revise_payload["failed_rules"]
    assert "chapter_text" not in revise_payload
    assert "patch_targets" in revise_payload
    assert [call.task_name for call in result.llm_calls] == ["plan", "draft", "revise", "truth_extract"]


def test_workflow_patch_revise_sends_local_window_not_full_chapter(config, book_workspace: Path) -> None:
    draft = no_hook_chapter_text(1000)
    revised_head = "门外传来异常声音，林默站在旧楼前，手里攥着登记表。"
    client = RevisionLoopMockClient(draft, draft.replace("林默站在旧楼前，手里攥着登记表。", revised_head, 1))
    workflow = ChapterWorkflow(config, client=client)

    result = run(workflow.run("lurenjia", 8, human_confirm=lambda _: True))

    assert result.status == ChapterStatus.EXPORTED
    assert result.audit is not None
    assert result.audit.passed is True
    revise_payload = client.calls[-1][1]
    assert revise_payload["mode"] == "spot_fix"
    assert "chapter_text" not in revise_payload
    assert "patch_targets" in revise_payload
    payload_text = str(revise_payload)
    assert draft not in payload_text
    assert "林默站在旧楼前" in revise_payload["patch_targets"][0]["window_text"]
    assert "门外传来异常声音" in result.text


def test_workflow_stops_after_two_failed_revision_rounds(config, book_workspace: Path) -> None:
    client = RevisionLoopMockClient("短稿", "仍然短")
    workflow = ChapterWorkflow(config, client=client)

    result = run(workflow.run("lurenjia", 8, human_confirm=lambda _: True))

    assert result.status == ChapterStatus.NEEDS_REVIEW
    assert result.error == "revision_exhausted"
    assert result.audit is not None
    assert result.audit.passed is False
    assert [task_name for task_name, _ in client.calls] == ["plan", "draft", "revise", "revise"]
