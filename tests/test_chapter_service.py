from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from storyforge3.config import StoryForge3Config
from storyforge3.models import ChapterIntent, ChapterStatus
from storyforge3.services.chapter_service import ChapterService
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
    text = run(service.draft("lurenjia", 8, intent))
    assert "林默" in text
    audit = run(service.audit("lurenjia", 8))
    assert audit.passed is True
    result = run(service.run_full_pipeline("lurenjia", 9, human_confirm=lambda _: True))
    assert result.status == ChapterStatus.EXPORTED


def test_chapter_service_plan_uses_registry_plan_template(config: StoryForge3Config, book_workspace: Path) -> None:
    llm = PlanPromptMockClient()
    service = ChapterService(config, llm=llm)

    intent = run(service.plan("lurenjia", 8))

    assert intent.goal == "林默进入检测中心。"
    call = llm.calls[0]
    assert call["task_name"] == "chapter_plan"
    assert "规划第8章" in call["system_prompt"]
    assert "不要输出章节正文" in call["system_prompt"]


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
