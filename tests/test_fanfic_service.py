from __future__ import annotations

import asyncio
import json
from pathlib import Path

from storyforge3.config import StoryForge3Config
from storyforge3.models import FanficMode
from storyforge3.services.fanfic_service import FanficService
from storyforge3.storage import BookStorage, StoragePaths


CANON_RESPONSE = """=== SECTION: world_rules ===
江城存在异常检测中心，普通人不能感知存在感残痕。

=== SECTION: character_profiles ===
| 角色 | 身份 | 性格底色 | 语癖/口头禅 | 说话风格 | 行为模式 | 关键关系 | 信息边界 |
|------|------|----------|-------------|----------|----------|----------|----------|
| 林默 | 高三学生 | 谨慎 | 先等等 | 短句，先观察后回应 | 遇事先确认出口 | 与许青互相试探 | 不知道副楼真相 |

=== SECTION: key_events ===
| 序号 | 事件 | 涉及角色 | 对同人写作的约束 |
|------|------|----------|------------------|
| 1 | 林默进入检测中心 | 林默、许青 | 后续不能假装从未见过 |

=== SECTION: power_system ===
存在感可以收敛，但过度使用会留下残痕。

=== SECTION: writing_style ===
短段落推进，常用动作外化心理。"""


def run(coro):
    return asyncio.run(coro)


class FanficLLM:
    def __init__(self, response: str = CANON_RESPONSE) -> None:
        self.response = response
        self.calls: list[dict] = []

    async def generate_text(self, task_name, system_prompt, user_payload, **kwargs):
        self.calls.append(
            {
                "task_name": task_name,
                "system_prompt": system_prompt,
                "payload": user_payload,
                "model": kwargs.get("model"),
                "temperature": kwargs.get("temperature"),
            }
        )
        return self.response


def make_service(tmp_path: Path, llm: FanficLLM) -> FanficService:
    config = StoryForge3Config(
        providers_config_dir=str(tmp_path / ".storyforge3"),
        books_dir=str(tmp_path / "books"),
        architect_model="canon-model",
    )
    paths = StoragePaths(Path(config.books_dir))
    return FanficService(llm, config, storage=BookStorage(paths.books_root), paths=paths)


def test_parse_sections_extracts_all_five_sections(tmp_path: Path) -> None:
    service = make_service(tmp_path, FanficLLM())

    sections = service._parse_sections(CANON_RESPONSE)

    assert sections["world_rules"].startswith("江城存在异常检测中心")
    assert "林默" in sections["character_profiles"]
    assert "后续不能假装从未见过" in sections["key_events"]
    assert "存在感可以收敛" in sections["power_system"]
    assert "短段落推进" in sections["writing_style"]


def test_import_canon_handles_missing_section_as_empty(tmp_path: Path) -> None:
    llm = FanficLLM("=== SECTION: world_rules ===\n江城规则。")
    service = make_service(tmp_path, llm)

    canon = run(service.import_canon("book", "原作文本", "原作A", FanficMode.CANON))

    assert canon.world_rules == "江城规则。"
    assert canon.character_profiles == ""
    assert canon.key_events == ""
    assert canon.power_system == ""
    assert canon.writing_style == ""
    assert "（素材中未提取到角色信息）" in canon.full_document


def test_import_canon_truncates_long_source(tmp_path: Path) -> None:
    llm = FanficLLM()
    service = make_service(tmp_path, llm)

    run(service.import_canon("book", "原" * 50_010, "长原作", FanficMode.AU))

    call = llm.calls[0]
    assert call["task_name"] == "fanfic_canon_import"
    assert call["model"] == "canon-model"
    assert call["temperature"] == 0.3
    assert len(call["payload"]["source_text"]) == 50_000
    assert "已截断" in call["system_prompt"]


def test_import_canon_saves_markdown_and_json(tmp_path: Path) -> None:
    llm = FanficLLM()
    service = make_service(tmp_path, llm)

    canon = run(service.import_canon("book", "原作文本", "原作A", FanficMode.CANON))
    loaded = service.get_canon("book")

    root = tmp_path / "books" / "book"
    assert (root / "fanfic_canon.md").read_text(encoding="utf-8") == canon.full_document
    data = json.loads((root / "fanfic_canon.json").read_text(encoding="utf-8"))
    assert data["mode"] == "canon"
    assert data["source_name"] == "原作A"
    assert loaded == canon


def test_get_canon_returns_none_when_absent(tmp_path: Path) -> None:
    service = make_service(tmp_path, FanficLLM())

    assert service.get_canon("missing") is None


def test_refresh_canon_preserves_mode_and_source_name(tmp_path: Path) -> None:
    llm = FanficLLM()
    service = make_service(tmp_path, llm)
    run(service.import_canon("book", "原作文本", "原作A", FanficMode.CP))
    llm.response = "=== SECTION: world_rules ===\n刷新后的规则。"

    refreshed = run(service.refresh_canon("book", "新文本"))

    assert refreshed.mode == FanficMode.CP
    assert refreshed.source_name == "原作A"
    assert refreshed.world_rules == "刷新后的规则。"
    assert llm.calls[-1]["payload"]["mode"] == "cp"
