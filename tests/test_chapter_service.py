from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from storyforge3.config import StoryForge3Config
from storyforge3.models import ChapterIntent, ChapterStatus, TruthData
from storyforge3.services.chapter_service import ChapterService
from storyforge3.state.machine import ChapterStateMachine
from storyforge3.style.imitation import StyleAnalyzer
from storyforge3.truth.database import TruthDatabase, TruthEntry


def run(coro):
    return asyncio.run(coro)


class MockClient:
    async def generate_text(self, task_name, system_prompt, user_payload, **kwargs):
        if task_name == "chapter_plan":
            return "本章目标：林默进入检测中心。"
        return (
            "林默站在副楼门口，听见走廊尽头传来短促的提示音。"
            "下一秒，咨询室里传来医生压低的声音：先别进来。"
        ) * 80

    async def generate_json(self, task_name, system_prompt, user_payload, response_schema, **kwargs):
        return {"fact_assertions": ["林默进入检测中心。"], "character_updates": [], "relationship_updates": [], "hook_updates": [], "irreversible_facts": [], "notes": []}


class DraftLengthMockClient:
    def __init__(self, *, draft_text: str, normalized_text: str) -> None:
        self.draft_text = draft_text
        self.normalized_text = normalized_text
        self.calls: list[dict] = []

    async def generate_text(self, task_name, system_prompt, user_payload, **kwargs):
        self.calls.append({"task_name": task_name, "system_prompt": system_prompt, "payload": user_payload, "model": kwargs.get("model")})
        if task_name == "chapter_plan":
            return "本章目标：林默进入检测中心。"
        if task_name == "length_normalize":
            return self.normalized_text
        if task_name == "chapter_draft_chunk_plan":
            return "1. 第一段\n2. 第二段"
        if task_name == "chapter_draft_chunk":
            return self.draft_text
        return self.draft_text


class PlanPromptMockClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def generate_text(self, task_name, system_prompt, user_payload, **kwargs):
        self.calls.append({"task_name": task_name, "system_prompt": system_prompt, "payload": user_payload})
        return "本章目标：林默进入检测中心。"


class ReviseMockClient:
    def __init__(self, replacement: str) -> None:
        self.replacement = replacement
        self.calls: list[dict] = []

    async def generate_text(self, task_name, system_prompt, user_payload, **kwargs):
        self.calls.append({"task_name": task_name, "system_prompt": system_prompt, "payload": user_payload, "kwargs": kwargs})
        if task_name == "chapter_plan":
            return "本章目标：林默进入检测中心。"
        return self.replacement

    async def generate_json(self, task_name, system_prompt, user_payload, response_schema, **kwargs):
        self.calls.append(
            {
                "task_name": task_name,
                "system_prompt": system_prompt,
                "payload": user_payload,
                "response_schema": response_schema,
                "kwargs": kwargs,
            }
        )
        if task_name == "revise":
            return {
                "patches": [
                    {
                        "find": "请注意，",
                        "replace": "这时，",
                        "rule_id": "forbidden_patterns",
                    }
                ]
            }
        return {"fact_assertions": ["林默进入检测中心。"], "character_updates": [], "relationship_updates": [], "hook_updates": [], "irreversible_facts": [], "notes": []}


def chinese_text(chars: int) -> str:
    return "林" * chars


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


def test_chapter_service_plan_draft_audit_and_run(config: StoryForge3Config, book_workspace: Path) -> None:
    service = ChapterService(config, llm=MockClient())
    intent = run(service.plan("lurenjia", 8))
    assert intent == ChapterIntent(8, "林默进入检测中心。", outline_node="本章目标：林默进入检测中心。")
    plan_path = service.paths.plan_file("lurenjia", 8)
    assert plan_path.exists()
    assert json.loads(plan_path.read_text(encoding="utf-8"))["goal"] == "林默进入检测中心。"
    assert ChapterStateMachine(service.paths.chapter_states("lurenjia")).current_status("lurenjia", 8) == ChapterStatus.PLANNED
    text = run(service.draft("lurenjia", 8, intent))
    assert "林默" in text
    audit = run(service.audit("lurenjia", 8))
    assert audit.passed is True
    result = run(service.run_full_pipeline("lurenjia", 9, human_confirm=lambda _: True))
    assert result.status == ChapterStatus.EXPORTED


def test_chapter_service_update_text_writes_atomically_and_marks_needs_review(
    config: StoryForge3Config,
    book_workspace: Path,
) -> None:
    chapter_path = book_workspace / "chapters" / "0007.md"
    original_text = chapter_path.read_text(encoding="utf-8")
    original_hash = hashlib.sha256(original_text.encode("utf-8")).hexdigest()[:8]
    service = ChapterService(config, llm=MockClient())

    result = run(service.update_text("lurenjia", 7, "林默改完这一章。", expected_hash=original_hash))

    assert result.status == ChapterStatus.NEEDS_REVIEW
    assert result.text == "林默改完这一章。"
    assert chapter_path.read_text(encoding="utf-8") == "林默改完这一章。"
    assert chapter_path.with_suffix(".before.md").read_text(encoding="utf-8") == original_text
    state_machine = ChapterStateMachine(service.paths.chapter_states("lurenjia"))
    assert state_machine.current_status("lurenjia", 7) == ChapterStatus.NEEDS_REVIEW
    assert state_machine.history("lurenjia", 7)[-1]["reason"] == "manual_edit"


def test_chapter_service_update_text_rejects_hash_conflicts(
    config: StoryForge3Config,
    book_workspace: Path,
) -> None:
    chapter_path = book_workspace / "chapters" / "0007.md"
    original_text = chapter_path.read_text(encoding="utf-8")
    service = ChapterService(config, llm=MockClient())

    try:
        run(service.update_text("lurenjia", 7, "林默改完这一章。", expected_hash="deadbeef"))
    except ValueError as exc:
        assert str(exc) == "章节内容已被修改，请刷新后重试"
    else:
        raise AssertionError("expected hash conflict")

    assert chapter_path.read_text(encoding="utf-8") == original_text


def test_chapter_service_update_text_rejects_missing_and_empty_chapters(
    config: StoryForge3Config,
    book_workspace: Path,
) -> None:
    (book_workspace / "chapters" / "0008.md").write_text("", encoding="utf-8")
    service = ChapterService(config, llm=MockClient())

    try:
        run(service.update_text("lurenjia", 99, "林默改完这一章。"))
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("expected missing chapter")

    try:
        run(service.update_text("lurenjia", 8, "林默改完这一章。"))
    except ValueError as exc:
        assert str(exc) == "空章节请先使用 draft 管线生成正文"
    else:
        raise AssertionError("expected empty chapter rejection")


def test_chapter_service_revise_writes_revised_text_snapshot_and_diff(
    config: StoryForge3Config,
    book_workspace: Path,
    sample_chapter_text: str,
) -> None:
    chapter_path = book_workspace / "chapters" / "0007.md"
    original_text = f"请注意，{sample_chapter_text}"
    revised_text = f"这时，{sample_chapter_text}"
    chapter_path.write_text(original_text, encoding="utf-8")
    service = ChapterService(config, llm=ReviseMockClient(revised_text))
    state_machine = ChapterStateMachine(service.paths.chapter_states("lurenjia"))
    state_machine.advance("lurenjia", 7, ChapterStatus.PLANNED)
    state_machine.advance("lurenjia", 7, ChapterStatus.DRAFTED)
    state_machine.advance("lurenjia", 7, ChapterStatus.AUDITED)

    result = run(service.revise("lurenjia", 7, mode="spot_fix"))

    assert result.status == ChapterStatus.REVISED
    assert result.text == revised_text
    assert chapter_path.read_text(encoding="utf-8") == revised_text
    assert chapter_path.with_suffix(".before.md").read_text(encoding="utf-8") == original_text
    assert result.revision_diff is not None
    assert result.revision_diff.summary.changed_blocks == 1
    assert result.revision_diff.blocks[0].kind == "replace"
    assert "请注意" in result.revision_diff.blocks[0].before_text
    assert "这时" in result.revision_diff.blocks[0].after_text
    assert result.error is not None
    assert "revision_mode=spot_fix" in result.error
    assert "mode_source=manual" in result.error
    assert state_machine.current_status("lurenjia", 7) == ChapterStatus.REVISED


def test_chapter_service_revise_returns_no_diff_when_audit_already_passed(
    config: StoryForge3Config,
    book_workspace: Path,
    sample_chapter_text: str,
) -> None:
    chapter_path = book_workspace / "chapters" / "0007.md"
    chapter_path.write_text(sample_chapter_text, encoding="utf-8")
    state_machine = ChapterStateMachine(Path(config.books_dir) / "state.json")
    state_machine.advance("lurenjia", 7, ChapterStatus.PLANNED)
    state_machine.advance("lurenjia", 7, ChapterStatus.DRAFTED)
    state_machine.advance("lurenjia", 7, ChapterStatus.AUDITED)
    service = ChapterService(config, llm=ReviseMockClient(sample_chapter_text))

    result = run(service.revise("lurenjia", 7))

    assert result.revision_diff is None
    assert result.error == "audit_passed_no_revision_needed"
    assert not chapter_path.with_suffix(".before.md").exists()


def test_chapter_service_plan_uses_registry_plan_template(config: StoryForge3Config, book_workspace: Path) -> None:
    llm = PlanPromptMockClient()
    service = ChapterService(config, llm=llm)

    intent = run(service.plan("lurenjia", 8))

    assert intent.goal == "林默进入检测中心。"
    call = llm.calls[0]
    assert call["task_name"] == "chapter_plan"
    assert "规划第8章" in call["system_prompt"]
    assert "不要输出章节正文" in call["system_prompt"]


def test_chapter_service_plan_is_idempotent(config: StoryForge3Config, book_workspace: Path) -> None:
    service = ChapterService(config, llm=MockClient())

    first = run(service.plan("lurenjia", 8))
    second = run(service.plan("lurenjia", 8))

    assert first.goal == second.goal
    assert ChapterStateMachine(service.paths.chapter_states("lurenjia")).current_status("lurenjia", 8) == ChapterStatus.PLANNED


def test_chapter_service_get_status_returns_planned_without_text(config: StoryForge3Config, book_workspace: Path) -> None:
    service = ChapterService(config, llm=MockClient())
    run(service.plan("lurenjia", 8))

    result = run(service.get_status("lurenjia", 8))

    assert result is not None
    assert result.status == ChapterStatus.PLANNED
    assert result.text == ""




def test_chapter_service_get_status_exposes_audit_result_after_audit(config: StoryForge3Config, book_workspace: Path) -> None:
    service = ChapterService(config, llm=MockClient())
    service.storage.write_text(service.paths.chapter_file("lurenjia", 8), "林默听见门外传来提示音。")
    machine = ChapterStateMachine(service.paths.chapter_states("lurenjia"))
    for status in (ChapterStatus.PLANNED, ChapterStatus.DRAFTED):
        machine.advance("lurenjia", 8, status)

    audit = run(service.audit("lurenjia", 8))
    result = run(service.get_status("lurenjia", 8))

    assert result is not None
    assert result.status == ChapterStatus.AUDITED
    assert result.audit_result == audit
    assert service.paths.audit_result_file("lurenjia", 8).is_file()

def test_chapter_service_get_status_loads_truth_after_truth_committed(config: StoryForge3Config, book_workspace: Path) -> None:
    service = ChapterService(config, llm=MockClient())
    service.storage.write_text(service.paths.chapter_file("lurenjia", 8), "林默确认事实。")
    truth = TruthData(
        chapter_no=8,
        source="runtime_native",
        fact_assertions=("林默确认事实。",),
        character_updates=(),
        relationship_updates=(),
        hook_updates=(),
        irreversible_facts=(),
        notes=(),
    )
    service.truth_store.save("lurenjia", truth)
    machine = ChapterStateMachine(service.paths.chapter_states("lurenjia"))
    for status in (ChapterStatus.PLANNED, ChapterStatus.DRAFTED, ChapterStatus.AUDITED, ChapterStatus.APPROVED, ChapterStatus.TRUTH_COMMITTED):
        machine.advance("lurenjia", 8, status)

    result = run(service.get_status("lurenjia", 8))

    assert result is not None
    assert result.status == ChapterStatus.TRUTH_COMMITTED
    assert result.truth == truth


def test_chapter_service_get_status_does_not_load_truth_for_approved(config: StoryForge3Config, book_workspace: Path) -> None:
    service = ChapterService(config, llm=MockClient())
    service.storage.write_text(service.paths.chapter_file("lurenjia", 8), "林默确认事实。")
    service.truth_store.save(
        "lurenjia",
        TruthData(
            chapter_no=8,
            source="runtime_native",
            fact_assertions=("林默确认事实。",),
            character_updates=(),
            relationship_updates=(),
            hook_updates=(),
            irreversible_facts=(),
            notes=(),
        ),
    )
    machine = ChapterStateMachine(service.paths.chapter_states("lurenjia"))
    for status in (ChapterStatus.PLANNED, ChapterStatus.DRAFTED, ChapterStatus.AUDITED, ChapterStatus.APPROVED):
        machine.advance("lurenjia", 8, status)

    result = run(service.get_status("lurenjia", 8))

    assert result is not None
    assert result.status == ChapterStatus.APPROVED
    assert result.truth is None


def test_chapter_service_draft_reuses_persisted_plan(config: StoryForge3Config, book_workspace: Path) -> None:
    llm = DraftLengthMockClient(draft_text=chinese_text(700), normalized_text=chinese_text(700))
    service = ChapterService(config, llm=llm)
    service.storage.write_json(
        service.paths.plan_file("lurenjia", 8),
        {
            "chapter_no": 8,
            "goal": "进入检测中心",
            "outline_node": "夜灯仓纠纷升级",
            "arc_context": "",
            "must_keep": ["保留巡夜队压力"],
            "must_avoid": ["直接解释世界观"],
            "style_emphasis": ["短句推进"],
        },
    )
    ChapterStateMachine(service.paths.chapter_states("lurenjia")).advance("lurenjia", 8, ChapterStatus.PLANNED)

    run(service.draft("lurenjia", 8))

    assert [call["task_name"] for call in llm.calls] == ["chapter_draft"]
    assert llm.calls[0]["payload"]["intent"] == "进入检测中心"
    # A successful draft advances the chapter status PLANNED -> DRAFTED so the UI
    # (and audit/revise gating) recognizes a draft artifact exists.
    assert ChapterStateMachine(service.paths.chapter_states("lurenjia")).current_status("lurenjia", 8) == ChapterStatus.DRAFTED


def test_chapter_service_plan_updates_current_chapter(config: StoryForge3Config, book_workspace: Path) -> None:
    write_book_meta(book_workspace, target_chars=1000)
    service = ChapterService(config, llm=MockClient())

    run(service.plan("lurenjia", 8))

    meta = json.loads((book_workspace / "book.json").read_text(encoding="utf-8"))
    assert meta["current_chapter"] == 8


def test_chapter_draft_uses_registry_compose_prompt(config: StoryForge3Config, book_workspace: Path) -> None:
    write_book_meta(book_workspace, target_chars=700)
    llm = DraftLengthMockClient(draft_text=chinese_text(700), normalized_text=chinese_text(700))
    service = ChapterService(config, llm=llm)

    run(service.draft("lurenjia", 8, ChapterIntent(8, "进入检测中心")))

    assert llm.calls[0]["task_name"] == "chapter_draft"
    assert "续写第8章" in llm.calls[0]["system_prompt"]
    assert "只输出章节正文" in llm.calls[0]["system_prompt"]


def test_chapter_service_draft_normalizes_text_outside_hard_range(config: StoryForge3Config, book_workspace: Path) -> None:
    write_book_meta(book_workspace, target_chars=700)
    llm = DraftLengthMockClient(draft_text=chinese_text(1000), normalized_text=chinese_text(700))
    service = ChapterService(config, llm=llm)

    text = run(service.draft("lurenjia", 8, ChapterIntent(8, "进入检测中心")))

    assert text == chinese_text(700)
    assert (book_workspace / "chapters" / "0008.md").read_text(encoding="utf-8") == chinese_text(700)
    assert [call["task_name"] for call in llm.calls] == ["chapter_draft", "length_normalize"]
    normalize_payload = llm.calls[-1]["payload"]
    assert normalize_payload["target_chars"] == 700
    assert normalize_payload["hard_range"] == [489, 910]


def test_chapter_service_draft_payload_includes_world_and_character_context(
    config: StoryForge3Config,
    book_workspace: Path,
) -> None:
    (book_workspace / "world.json").write_text(
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
    (book_workspace / "characters.json").write_text(
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
    llm = DraftLengthMockClient(draft_text=chinese_text(1000), normalized_text=chinese_text(1000))
    service = ChapterService(config, llm=llm)

    run(service.draft("lurenjia", 8, ChapterIntent(8, "进入检测中心")))

    draft_payload = llm.calls[0]["payload"]
    assert draft_payload["world"] == {
        "setting": "存在感系统影响人群注意力",
        "power_system": "异常等级由检测中心记录",
        "core_conflict": "林默必须隐藏能力又接受检测",
    }
    assert draft_payload["characters"] == [
        {"name": "林默", "role": "protagonist", "profile": "高三学生，能力是调节自己的存在感", "personality": "谨慎但不懦弱"},
        {"name": "许青", "role": "major", "profile": "异常检测中心实习记录员", "personality": "细心，善于观察"},
    ]


def test_chapter_service_draft_injects_fanfic_context(
    config: StoryForge3Config,
    book_workspace: Path,
) -> None:
    write_book_meta(book_workspace, target_chars=700)
    meta = json.loads((book_workspace / "book.json").read_text(encoding="utf-8"))
    meta["fanfic_mode"] = "canon"
    (book_workspace / "book.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    (book_workspace / "fanfic_canon.md").write_text(
        """# 同人正典（《原作A》）

## 世界规则
江城存在异常检测中心。

## 角色档案
| 角色 | 身份 | 性格底色 | 语癖/口头禅 | 说话风格 | 行为模式 | 关键关系 | 信息边界 |
|------|------|----------|-------------|----------|----------|----------|----------|
| 林默 | 高三学生 | 谨慎 | 先等等 | 短句，先观察后回应 | 遇事先确认出口 | 与许青互相试探 | 不知道副楼真相 |
""",
        encoding="utf-8",
    )
    (book_workspace / "fanfic_canon.json").write_text(
        json.dumps(
            {
                "book_id": "lurenjia",
                "source_name": "原作A",
                "mode": "canon",
                "world_rules": "江城存在异常检测中心。",
                "character_profiles": "| 角色 | 身份 | 性格底色 | 语癖/口头禅 | 说话风格 | 行为模式 | 关键关系 | 信息边界 |\n|------|------|----------|-------------|----------|----------|----------|----------|\n| 林默 | 高三学生 | 谨慎 | 先等等 | 短句，先观察后回应 | 遇事先确认出口 | 与许青互相试探 | 不知道副楼真相 |",
                "key_events": "林默进入检测中心。",
                "power_system": "存在感系统。",
                "writing_style": "短段落推进。",
                "full_document": (book_workspace / "fanfic_canon.md").read_text(encoding="utf-8"),
                "generated_at": "2026-06-09T00:00:00+00:00",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    llm = DraftLengthMockClient(draft_text=chinese_text(700), normalized_text=chinese_text(700))
    service = ChapterService(config, llm=llm)

    run(service.draft("lurenjia", 8, ChapterIntent(8, "进入检测中心")))

    draft_payload = llm.calls[0]["payload"]
    assert "同人正典参照" in draft_payload["fanfic_canon"]
    assert "原作向同人" in draft_payload["fanfic_canon"]
    assert "角色语音参照" in draft_payload["character_voice_profiles"]
    assert "先等等" in draft_payload["character_voice_profiles"]
    assert "正典合规检查" in draft_payload["fanfic_mode_instructions"]


def test_chapter_service_draft_omits_fanfic_context_for_original_books(
    config: StoryForge3Config,
    book_workspace: Path,
) -> None:
    write_book_meta(book_workspace, target_chars=700)
    llm = DraftLengthMockClient(draft_text=chinese_text(700), normalized_text=chinese_text(700))
    service = ChapterService(config, llm=llm)

    run(service.draft("lurenjia", 8, ChapterIntent(8, "进入检测中心")))

    draft_payload = llm.calls[0]["payload"]
    assert "fanfic_canon" not in draft_payload
    assert "character_voice_profiles" not in draft_payload
    assert "fanfic_mode_instructions" not in draft_payload


def test_chapter_service_draft_payload_uses_retrieved_truth(
    config: StoryForge3Config,
    book_workspace: Path,
) -> None:
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
    llm = DraftLengthMockClient(draft_text=chinese_text(1000), normalized_text=chinese_text(1000))
    service = ChapterService(config, llm=llm)

    run(service.draft("lurenjia", 8, ChapterIntent(8, "林默和许青讨论残痕")))

    draft_payload = llm.calls[0]["payload"]
    assert "许青发现林默的存在感残痕。" in draft_payload["relevant_truth"]
    assert "fact_assertions" not in draft_payload["relevant_truth"]


def test_chapter_service_injects_style_fingerprint_prompt(config: StoryForge3Config, book_workspace: Path) -> None:
    fingerprint = StyleAnalyzer().analyze("林默停在门口。\n\n“先等等。”许青说。\n\n灯影压下来，他没有立刻回答。")
    write_book_meta(book_workspace, target_chars=700)
    meta = json.loads((book_workspace / "book.json").read_text(encoding="utf-8"))
    meta["style_fingerprint"] = asdict(fingerprint)
    (book_workspace / "book.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    llm = DraftLengthMockClient(draft_text=chinese_text(700), normalized_text=chinese_text(700))
    service = ChapterService(config, llm=llm)

    run(service.draft("lurenjia", 8, ChapterIntent(8, "进入检测中心")))

    system_prompt = llm.calls[0]["system_prompt"]
    assert "风格模仿指南" in system_prompt
    assert "平均句长" in system_prompt
    assert "对话占比" in system_prompt


def test_chapter_service_draft_skips_normalization_inside_hard_range(config: StoryForge3Config, book_workspace: Path) -> None:
    write_book_meta(book_workspace, target_chars=700)
    llm = DraftLengthMockClient(draft_text=chinese_text(900), normalized_text=chinese_text(700))
    service = ChapterService(config, llm=llm)

    text = run(service.draft("lurenjia", 8, ChapterIntent(8, "进入检测中心")))

    assert text == chinese_text(900)
    assert (book_workspace / "chapters" / "0008.md").read_text(encoding="utf-8") == chinese_text(900)
    assert [call["task_name"] for call in llm.calls] == ["chapter_draft"]


def test_chapter_service_uses_chunked_draft_above_threshold(config: StoryForge3Config, book_workspace: Path) -> None:
    write_book_meta(book_workspace, target_chars=1200)
    llm = DraftLengthMockClient(draft_text=chinese_text(500), normalized_text=chinese_text(1200))
    service = ChapterService(config, llm=llm)

    text = run(service.draft("lurenjia", 8, ChapterIntent(8, "进入检测中心")))

    assert text == f"{chinese_text(500)}\n\n{chinese_text(500)}"
    assert [call["task_name"] for call in llm.calls] == [
        "chapter_draft_chunk_plan",
        "chapter_draft_chunk",
        "chapter_draft_chunk",
    ]
    first_chunk_payload = llm.calls[1]["payload"]
    second_chunk_payload = llm.calls[2]["payload"]
    assert first_chunk_payload["target_chars"] == 1200
    assert first_chunk_payload["chunk_outline"] == "第一段"
    assert first_chunk_payload["previous_chunk_tail"] == ""
    assert second_chunk_payload["previous_chunk_tail"] == chinese_text(200)
