from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from storyforge3.api.deps import get_audit_service, get_config, get_truth_service
from storyforge3.audit.llm_auditor import LLMAuditIssue, LLMAuditResult
from storyforge3.models import AuditResult, TruthData
from storyforge3.prompts.registry import create_default_registry
from storyforge3.style.contract import DEFAULT_STYLE_CONTRACT, StyleContract
from storyforge3.style.guard import StyleGuardReport


def run(coro):
    return asyncio.run(coro)


class FakeLLMAuditor:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def audit(self, **kwargs) -> LLMAuditResult:
        assert kwargs["chapter_text"] == "林默进入检测中心。"
        self.calls.append(kwargs)
        return LLMAuditResult(
            passed=True,
            issues=(
                LLMAuditIssue(
                    severity="warning",
                    dimension="情节逻辑",
                    description="转折略快",
                    suggestion="增加动作承接",
                ),
            ),
        )


def truth(chapter_no: int) -> TruthData:
    return TruthData(
        chapter_no=chapter_no,
        source="runtime_native",
        fact_assertions=(f"第{chapter_no}章事实。",),
        character_updates=(),
        relationship_updates=(),
        hook_updates=(),
        irreversible_facts=(),
        notes=(),
    )


def test_audit_service_run_mechanical(config) -> None:
    from storyforge3.services.audit_service import AuditService

    service = AuditService(config=config)

    result = service.run_mechanical(1, "今天天气不错，林默走在路上。")

    assert isinstance(result, AuditResult)
    assert result.chapter_no == 1
    assert result.blocking_issues


def test_audit_service_run_llm_audit(config) -> None:
    from storyforge3.services.audit_service import AuditService

    auditor = FakeLLMAuditor()
    service = AuditService(config=config, llm_auditor=auditor)

    result = run(service.run_llm_audit("林默进入检测中心。", "世界观上下文"))

    assert isinstance(result, LLMAuditResult)
    assert result.passed is True
    assert result.issues[0].dimension == "情节逻辑"
    assert auditor.calls[0]["extra_context"] == "世界观上下文"


def test_audit_service_run_llm_audit_injects_fanfic_context(config) -> None:
    from storyforge3.services.audit_service import AuditService

    root = Path(config.books_dir) / "lurenjia"
    root.mkdir(parents=True)
    (root / "book.json").write_text(
        (
            "{"
            '"book_id":"lurenjia","title":"同人书","genre":"fanfic","platform":"tomato",'
            '"status":"incubating","target_chapters":10,"chapter_word_count":2000,'
            '"language":"zh","current_chapter":0,"created_at":"","updated_at":"","fanfic_mode":"canon"'
            "}"
        ),
        encoding="utf-8",
    )
    (root / "fanfic_canon.json").write_text(
        (
            "{"
            '"book_id":"lurenjia","source_name":"原作A","mode":"canon",'
            '"world_rules":"江城存在异常检测中心。",'
            '"character_profiles":"| 角色 | 身份 | 性格底色 | 语癖/口头禅 | 说话风格 | 行为模式 | 关键关系 | 信息边界 |\\n'
            '|------|------|----------|-------------|----------|----------|----------|----------|\\n'
            '| 林默 | 高三学生 | 谨慎 | 先等等 | 短句 | 先观察 | 互相试探 | 不知道副楼真相 |",'
            '"key_events":"林默进入检测中心。","power_system":"存在感系统。",'
            '"writing_style":"短段落推进。","full_document":"# 同人正典\\n\\n## 世界规则\\n江城存在异常检测中心。",'
            '"generated_at":"2026-06-09T00:00:00+00:00"'
            "}"
        ),
        encoding="utf-8",
    )
    auditor = FakeLLMAuditor()
    service = AuditService(config=config, llm_auditor=auditor)

    run(service.run_llm_audit("林默进入检测中心。", "基础上下文", book_id="lurenjia"))

    call = auditor.calls[0]
    assert "基础上下文" in call["extra_context"]
    assert "同人审计模式：canon" in call["extra_context"]
    assert "角色还原度" in call["extra_context"]
    assert "正典合规检查" in call["extra_context"]


def test_truth_service_save_and_load(config) -> None:
    from storyforge3.services.truth_service import TruthService

    service = TruthService(config=config)
    item = truth(2)

    service.save("lurenjia", item)

    assert service.load_latest("lurenjia") == item


def test_truth_service_load_history(config) -> None:
    from storyforge3.services.truth_service import TruthService

    service = TruthService(config=config)
    for chapter_no in range(1, 4):
        service.save("lurenjia", truth(chapter_no))

    history = service.load_history("lurenjia")

    assert [item.chapter_no for item in history] == [1, 2, 3]


def test_truth_service_load_history_empty(config) -> None:
    from storyforge3.services.truth_service import TruthService

    assert TruthService(config=config).load_history("missing") == []


def test_prompt_service_get_latest() -> None:
    from storyforge3.services.prompt_service import PromptService

    template = PromptService(create_default_registry()).get("compose")

    assert template.task_type == "compose"
    assert template.version == 1


def test_prompt_service_list_templates() -> None:
    from storyforge3.services.prompt_service import PromptService

    templates = PromptService(create_default_registry()).list_templates()
    by_task = {item["task_type"]: item["versions"] for item in templates}

    assert "compose" in by_task
    assert "truth_extract" in by_task
    assert by_task["truth_extract"] == [2]


def test_style_service_default_contract(config) -> None:
    from storyforge3.services.style_service import StyleService

    assert StyleService(config).get_contract("missing") == DEFAULT_STYLE_CONTRACT


def test_style_service_save_and_load_contract(config) -> None:
    from storyforge3.services.style_service import StyleService

    service = StyleService(config)
    contract = StyleContract(
        contract_id="custom-v1",
        display_name="自定义风格",
        dialogue_density=(0.1, 0.3),
        narration_ratio=(0.6, 0.9),
        sentence_length_range=(6, 24),
        banned_phrases=("本章",),
        fatigue_words=("突然",),
        required_traits=("短句推进",),
        character_voice_hints={"林默": ("谨慎", "短句")},
    )

    service.save_contract("lurenjia", contract)

    assert service.get_contract("lurenjia") == contract


def test_style_service_check_compliance(config) -> None:
    from storyforge3.services.style_service import StyleService

    result = StyleService(config).check_compliance("林默站住。", DEFAULT_STYLE_CONTRACT)

    assert isinstance(result, StyleGuardReport)
    assert result.contract_id == DEFAULT_STYLE_CONTRACT.contract_id


def test_deps_inject_audit_service(config) -> None:
    app = FastAPI()

    @app.get("/audit")
    def endpoint(service=Depends(get_audit_service)):
        return {"service": service.__class__.__name__}

    app.dependency_overrides[get_config] = lambda: config
    try:
        response = TestClient(app).get("/audit")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"service": "AuditService"}


def test_deps_inject_truth_service(config) -> None:
    app = FastAPI()

    @app.get("/truth")
    def endpoint(service=Depends(get_truth_service)):
        return {"service": service.__class__.__name__}

    app.dependency_overrides[get_config] = lambda: config
    try:
        response = TestClient(app).get("/truth")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"service": "TruthService"}
