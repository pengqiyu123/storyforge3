from __future__ import annotations

import json
from pathlib import Path

from storyforge3.config import StoryForge3Config
from storyforge3.services.style_service import StyleService
from storyforge3.style.contract import DEFAULT_STYLE_CONTRACT, StyleContract


def book_meta_path(config: StoryForge3Config, book_id: str = "lurenjia") -> Path:
    return Path(config.books_dir) / book_id / "book.json"


def test_get_contract_returns_default_when_book_metadata_missing(config: StoryForge3Config) -> None:
    service = StyleService(config)

    contract = service.get_contract("missing-book")

    assert contract == DEFAULT_STYLE_CONTRACT


def test_save_contract_creates_book_metadata(config: StoryForge3Config) -> None:
    service = StyleService(config)
    contract = StyleContract(
        contract_id="custom-v1",
        display_name="自定义风格",
        banned_phrases=("剧情",),
        required_traits=("动作推进",),
    )

    service.save_contract("lurenjia", contract)

    data = json.loads(book_meta_path(config).read_text(encoding="utf-8"))
    assert data["style_contract"]["contract_id"] == "custom-v1"
    assert data["style_contract"]["display_name"] == "自定义风格"
    assert data["style_contract"]["banned_phrases"] == ["剧情"]


def test_get_contract_reads_saved_contract(config: StoryForge3Config) -> None:
    service = StyleService(config)
    contract = StyleContract(
        contract_id="custom-v2",
        display_name="读取风格",
        dialogue_density=(0.1, 0.3),
        narration_ratio=(0.7, 0.9),
        sentence_length_range=(6, 30),
        banned_phrases=("本章", "剧情"),
        fatigue_words=("突然",),
        required_traits=("线索可见",),
        description="测试契约",
        version=2,
        prompt_extra="保持悬疑。",
        character_voice_hints={"林默": ("克制", "短句")},
    )
    service.save_contract("lurenjia", contract)

    loaded = service.get_contract("lurenjia")

    assert loaded == contract


def test_get_contract_falls_back_when_style_contract_is_not_object(config: StoryForge3Config) -> None:
    path = book_meta_path(config)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"style_contract": "bad-data"}), encoding="utf-8")

    contract = StyleService(config).get_contract("lurenjia")

    assert contract == DEFAULT_STYLE_CONTRACT


def test_get_contract_falls_back_when_contract_fields_are_invalid(config: StoryForge3Config) -> None:
    path = book_meta_path(config)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"style_contract": {"contract_id": "broken", "version": "not-an-int"}}),
        encoding="utf-8",
    )

    contract = StyleService(config).get_contract("lurenjia")

    assert contract == DEFAULT_STYLE_CONTRACT


def test_save_contract_preserves_existing_metadata(config: StoryForge3Config) -> None:
    path = book_meta_path(config)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"title": "我是路人甲", "status": "active"}), encoding="utf-8")
    contract = StyleContract(contract_id="custom-v3", display_name="保存风格")

    StyleService(config).save_contract("lurenjia", contract)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["title"] == "我是路人甲"
    assert data["status"] == "active"
    assert data["style_contract"]["contract_id"] == "custom-v3"
    assert data["style_contract"]["display_name"] == "保存风格"
    assert data["style_contract"]["dialogue_density"] == [0.2, 0.45]


def test_check_compliance_returns_style_guard_report() -> None:
    contract = StyleContract(
        contract_id="strict",
        display_name="Strict",
        dialogue_density=(0.2, 0.6),
        banned_phrases=("剧情",),
    )

    report = StyleService(StoryForge3Config()).check_compliance("本章剧情需要说明。", contract)

    assert report.contract_id == "strict"
    assert report.passed is False
    assert any(item.rule_name == "banned_phrases" for item in report.violations)
