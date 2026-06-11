from __future__ import annotations

import asyncio
import json
from pathlib import Path

from storyforge3.config import StoryForge3Config
from storyforge3.models import ShortStoryConfig, ShortStoryStatus
from storyforge3.services.short_story_service import ShortStoryService
from storyforge3.storage import BookStorage, StoragePaths


PLAN_TEXT = """## 核心设定
一名便利店夜班店员发现每晚 3:17 都会有不存在的顾客结账。

## 开篇设计
从收银机自动弹开的抽屉切入，主角发现监控里没有顾客。

## 高潮设计
不存在的顾客留下真实纸币，主角必须决定是否跟随纸币上的地址。

## 结尾设计
主角在天亮前烧掉纸币，但收银机里多了一张自己的工牌。

## 角色
林默：夜班店员，谨慎但会追查异常。
许青：白班店员，只在交接班时出现。

## 关键场景
- 收银机在 3:17 自动弹开
- 监控画面缺失三秒
- 纸币背面浮现地址
- 主角烧掉纸币后发现工牌"""


def run(coro):
    return asyncio.run(coro)


class ShortStoryLLM:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def generate_text(self, task_name, system_prompt, user_payload, **kwargs):
        self.calls.append(
            {
                "task_name": task_name,
                "system_prompt": system_prompt,
                "payload": user_payload,
                "model": kwargs.get("model"),
                "prompt_version": kwargs.get("prompt_version"),
            }
        )
        if task_name == "short_plan":
            return PLAN_TEXT
        if task_name == "short_draft_chunk_plan":
            return "1. 开篇异常\n2. 纸币地址"
        if task_name == "short_draft_chunk":
            return "林默站在收银台后，抽屉忽然弹开。\n\n监控屏幕黑了三秒。"
        if task_name == "short_draft":
            return "林默站在收银台后，抽屉忽然弹开。\n\n监控屏幕黑了三秒。\n\n纸币背面浮出一行地址。"
        return "短篇正文。"

    async def generate_json(self, task_name, system_prompt, user_payload, response_schema, **kwargs):
        self.calls.append(
            {
                "task_name": task_name,
                "system_prompt": system_prompt,
                "payload": user_payload,
                "schema": response_schema,
                "model": kwargs.get("model"),
            }
        )
        if task_name == "short_revise":
            return {"patches": [{"find": "抽屉忽然弹开", "replace": "抽屉突然自己弹开", "rule_id": "golden_three_hook"}]}
        return {"issues": []}


def make_service(tmp_path: Path, llm: ShortStoryLLM | None = None) -> ShortStoryService:
    config = StoryForge3Config(
        providers_config_dir=str(tmp_path / ".storyforge3"),
        books_dir=str(tmp_path / "books"),
        planner_model="plan-model",
        writer_model="write-model",
        auditor_model="audit-model",
    )
    paths = StoragePaths(Path(config.books_dir))
    return ShortStoryService(config, llm=llm or ShortStoryLLM(), storage=BookStorage(paths.books_root), paths=paths)


def test_create_short_story_saves_meta(tmp_path: Path) -> None:
    service = make_service(tmp_path)

    meta = run(
        service.create(
            ShortStoryConfig(
                title="凌晨三点十七",
                genre="horror",
                target_chars=6000,
                premise="便利店夜班遇到不存在的顾客。",
                style="悬疑克制",
            )
        )
    )

    assert meta.status == ShortStoryStatus.EMPTY
    assert meta.book_id.startswith("story_")
    data = json.loads((tmp_path / "books" / meta.book_id / "short_story.json").read_text(encoding="utf-8"))
    assert data["title"] == "凌晨三点十七"
    assert data["target_chars"] == 6000
    assert data["premise"] == "便利店夜班遇到不存在的顾客。"


def test_list_stories_returns_short_story_metadata(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    first = run(service.create(ShortStoryConfig("Night Shift", "horror", 6000, "便利店怪谈", "")))
    second = run(service.create(ShortStoryConfig("Sky Gate", "sci-fi", 9000, "空港异常", "")))
    unrelated = tmp_path / "books" / "ordinary-book"
    unrelated.mkdir(parents=True)
    (unrelated / "book.json").write_text("{}", encoding="utf-8")

    stories = service.list_stories()

    assert [story.book_id for story in stories] == [first.book_id, second.book_id]
    assert [story.title for story in stories] == ["Night Shift", "Sky Gate"]


def test_plan_generates_short_plan(tmp_path: Path) -> None:
    llm = ShortStoryLLM()
    service = make_service(tmp_path, llm)
    meta = run(service.create(ShortStoryConfig("凌晨三点十七", "horror", 6000, "夜班怪谈", "悬疑")))

    plan = run(service.plan(meta.book_id))

    assert plan.book_id == meta.book_id
    assert "不存在的顾客" in plan.premise
    assert "监控里没有顾客" in plan.opening
    assert "跟随纸币上的地址" in plan.climax
    assert "自己的工牌" in plan.ending
    assert plan.key_scenes == ("收银机在 3:17 自动弹开", "监控画面缺失三秒", "纸币背面浮现地址", "主角烧掉纸币后发现工牌")
    assert llm.calls[0]["task_name"] == "short_plan"
    assert "短篇小说规划师" in llm.calls[0]["system_prompt"]
    assert llm.calls[0]["model"] == "plan-model"


def test_draft_generates_full_text(tmp_path: Path) -> None:
    llm = ShortStoryLLM()
    service = make_service(tmp_path, llm)
    meta = run(service.create(ShortStoryConfig("凌晨三点十七", "horror", 6000, "夜班怪谈", "悬疑")))
    run(service.plan(meta.book_id))

    text = run(service.draft(meta.book_id))

    assert "纸币背面浮出一行地址" in text
    assert (tmp_path / "books" / meta.book_id / "short_text.md").read_text(encoding="utf-8") == text
    assert [call["task_name"] for call in llm.calls] == ["short_plan", "short_draft"]
    assert llm.calls[-1]["payload"]["target_chars"] == 6000


def test_draft_uses_chunked_for_long_stories(tmp_path: Path) -> None:
    llm = ShortStoryLLM()
    service = make_service(tmp_path, llm)
    meta = run(service.create(ShortStoryConfig("长短篇", "sci-fi", 12_000, "太空站异常", "")))
    run(service.plan(meta.book_id))

    text = run(service.draft(meta.book_id))

    assert "监控屏幕黑了三秒" in text
    assert [call["task_name"] for call in llm.calls] == [
        "short_plan",
        "short_draft_chunk_plan",
        "short_draft_chunk",
        "short_draft_chunk",
        "short_draft_chunk",
        "short_draft_chunk",
        "short_draft_chunk",
        "short_draft_chunk",
    ]


def test_audit_reuses_existing_rules(tmp_path: Path) -> None:
    llm = ShortStoryLLM()
    service = make_service(tmp_path, llm)
    meta = run(service.create(ShortStoryConfig("审计短篇", "urban", 6000, "异常便利店", "")))
    run(service.plan(meta.book_id))
    run(service.draft(meta.book_id))

    audit = run(service.audit(meta.book_id))

    assert audit.chapter_no == 1
    assert len(audit.rule_results) >= 30
    assert llm.calls[-1]["task_name"] == "llm_audit"
    assert (tmp_path / "books" / meta.book_id / "short_story.json").read_text(encoding="utf-8").count("audited") == 1


def test_revise_uses_patch_mode_max_one_round(tmp_path: Path) -> None:
    llm = ShortStoryLLM()
    service = make_service(tmp_path, llm)
    meta = run(service.create(ShortStoryConfig("修订短篇", "horror", 6000, "异常便利店", "")))
    run(service.plan(meta.book_id))
    service._save_text(meta.book_id, "林默走进便利店。\n\n收银台很安静。\n\n抽屉忽然弹开。")

    result = run(service.revise(meta.book_id))

    assert result.status == ShortStoryStatus.REVISED
    assert "抽屉突然自己弹开" in result.text
    assert [call["task_name"] for call in llm.calls] == ["short_plan", "short_revise"]
    assert llm.calls[-1]["payload"]["revision_round"] == 1
    assert llm.calls[-1]["payload"]["mode"] == "patch"


def test_export_single_file(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    meta = run(service.create(ShortStoryConfig("导出短篇", "urban", 6000, "异常便利店", "")))
    service._save_text(meta.book_id, "林默站在收银台后。\n\n抽屉突然弹开。")

    path = run(service.export(meta.book_id, "md"))

    assert path.name == "short.md"
    assert "# 导出短篇" in path.read_text(encoding="utf-8")
    assert "抽屉突然弹开" in path.read_text(encoding="utf-8")


def test_run_full_pipeline_end_to_end(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    meta = run(service.create(ShortStoryConfig("完整短篇", "horror", 6000, "夜班怪谈", "悬疑")))

    result = run(service.run_full_pipeline(meta.book_id))

    assert result.status == ShortStoryStatus.EXPORTED
    assert result.audit is not None
    assert (tmp_path / "books" / meta.book_id / "exports" / "short.tomato.txt").is_file()


def test_get_status_returns_none_for_unknown(tmp_path: Path) -> None:
    service = make_service(tmp_path)

    assert service.get_status("missing") is None
