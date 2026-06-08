from __future__ import annotations

import asyncio
from pathlib import Path

from storyforge3.audit.llm_auditor import LLMAuditIssue, LLMAuditor, LLMAuditResult
from storyforge3.config import StoryForge3Config
from storyforge3.models import Character, CharacterRole, TruthData, WorldConfig
from storyforge3.prompts.registry import create_default_registry
from storyforge3.services.chapter_service import ChapterService
from storyforge3.storage import BookStorage, StoragePaths
from storyforge3.truth.store import TruthStore


def run(coro):
    return asyncio.run(coro)


class MockAuditLLM:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def generate_json(self, task_name, system_prompt, user_payload, response_schema, **kwargs):
        self.calls.append(
            {
                "task_name": task_name,
                "system_prompt": system_prompt,
                "payload": user_payload,
                "model": kwargs.get("model"),
                "prompt_version": kwargs.get("prompt_version"),
            }
        )
        return {
            "issues": [
                {
                    "severity": "critical",
                    "dimension": "OOC",
                    "description": "林默突然主动挑衅，和谨慎设定冲突。",
                    "suggestion": "改为被迫回应。",
                }
            ]
        }


def test_llm_auditor_parses_structured_issues() -> None:
    llm = MockAuditLLM()
    result = run(
        LLMAuditor(llm, create_default_registry(), StoryForge3Config(auditor_model="audit-model")).audit(
            chapter_text="林默冲进检测中心。",
            characters=(Character("book", "林默", CharacterRole.PROTAGONIST, "高三学生", "谨慎"),),
            world=WorldConfig("book", "江城", "存在感系统", "异常检测", ("能力不能凭空升级",)),
            previous_truth=TruthData(1, "runtime_native", ("林默很谨慎。",), (), (), (), (), ()),
        )
    )
    assert result == LLMAuditResult(
        passed=False,
        issues=(
            LLMAuditIssue(
                severity="critical",
                dimension="OOC",
                description="林默突然主动挑衅，和谨慎设定冲突。",
                suggestion="改为被迫回应。",
            ),
        ),
    )
    assert llm.calls[0]["task_name"] == "llm_audit"
    assert llm.calls[0]["model"] == "audit-model"
    assert {"OOC", "战力一致性", "信息边界", "情节逻辑"}.issubset(set(llm.calls[0]["payload"]["dimensions"]))


def test_default_registry_has_llm_audit_prompt() -> None:
    registry = create_default_registry()
    template = registry.get_latest("llm_audit")
    rendered = registry.render_system_prompt(template)
    assert "OOC" in rendered
    assert "结构化 JSON" in rendered


def test_chapter_service_run_llm_audit_loads_book_context(config: StoryForge3Config, tmp_path: Path) -> None:
    paths = StoragePaths(Path(config.books_dir))
    storage = BookStorage(paths.books_root)
    storage.write_json(
        paths.world_config("book"),
        {
            "book_id": "book",
            "setting": "江城",
            "power_system": "存在感系统",
            "core_conflict": "异常检测",
            "rules": ["能力不能凭空升级"],
        },
    )
    storage.write_json(
        paths.characters("book"),
        {
            "characters": [
                {
                    "book_id": "book",
                    "name": "林默",
                    "role": "protagonist",
                    "profile": "高三学生",
                    "personality": "谨慎",
                    "abilities": ["存在感调节"],
                    "arc_direction": "",
                }
            ]
        },
    )
    TruthStore(config.books_dir).save("book", TruthData(1, "runtime_native", ("林默预约检测。",), (), (), (), (), ()))
    llm = MockAuditLLM()
    result = run(ChapterService(config, llm=llm, storage=storage, paths=paths).run_llm_audit("book", 2, "林默进入检测中心。"))
    assert result.issues[0].dimension == "OOC"
    assert llm.calls[0]["payload"]["world_rules"] == ["能力不能凭空升级"]
    assert llm.calls[0]["payload"]["previous_truth"] == ["林默预约检测。"]
