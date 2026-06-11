from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from storyforge3.config import StoryForge3Config
from storyforge3.style.contract import DEFAULT_STYLE_CONTRACT, StyleContract
from storyforge3.style.guard import StyleGuard, StyleGuardReport


class StyleService:
    """风格契约与合规检查服务。"""

    def __init__(self, config: StoryForge3Config) -> None:
        self._books_dir = Path(config.books_dir)

    def get_contract(self, book_id: str) -> StyleContract:
        """获取书籍风格契约；未配置时返回默认契约。"""
        path = self._book_meta_path(book_id)
        if not path.exists():
            return DEFAULT_STYLE_CONTRACT
        data = json.loads(path.read_text(encoding="utf-8"))
        contract_data = data.get("style_contract")
        if not isinstance(contract_data, dict):
            return DEFAULT_STYLE_CONTRACT
        try:
            return StyleContract(
                contract_id=str(contract_data.get("contract_id", "custom")),
                display_name=str(contract_data.get("display_name", "自定义")),
                dialogue_density=_tuple_float_pair(contract_data.get("dialogue_density"), (0.2, 0.45)),
                narration_ratio=_tuple_float_pair(contract_data.get("narration_ratio"), (0.35, 0.8)),
                sentence_length_range=_tuple_int_pair(contract_data.get("sentence_length_range"), (8, 45)),
                banned_phrases=_tuple_str(contract_data.get("banned_phrases")),
                fatigue_words=_tuple_str(contract_data.get("fatigue_words")),
                required_traits=_tuple_str(contract_data.get("required_traits")),
                description=str(contract_data.get("description", "")),
                version=int(contract_data.get("version", 1)),
                prompt_extra=str(contract_data.get("prompt_extra", "")),
                character_voice_hints=_voice_hints(contract_data.get("character_voice_hints")),
            )
        except (TypeError, ValueError):
            return DEFAULT_STYLE_CONTRACT

    def check_compliance(self, text: str, contract: StyleContract) -> StyleGuardReport:
        """检查文本是否符合风格契约。"""
        return StyleGuard(contract).check(text)

    def save_contract(self, book_id: str, contract: StyleContract) -> None:
        """保存风格契约到 book.json。"""
        path = self._book_meta_path(book_id)
        data = {}
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
        data["style_contract"] = asdict(contract)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def _book_meta_path(self, book_id: str) -> Path:
        return self._books_dir / book_id / "book.json"


def _tuple_str(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(item) for item in value)


def _tuple_float_pair(value: object, default: tuple[float, float]) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return default
    return (float(value[0]), float(value[1]))


def _tuple_int_pair(value: object, default: tuple[int, int]) -> tuple[int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return default
    return (int(value[0]), int(value[1]))


def _voice_hints(value: object) -> dict[str, tuple[str, ...]]:
    if not isinstance(value, dict):
        return {}
    return {str(key): _tuple_str(items) for key, items in value.items()}
