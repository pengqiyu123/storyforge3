from __future__ import annotations

import json
from pathlib import Path

import pytest

from storyforge3.config import StoryForge3Config


@pytest.fixture
def config(tmp_path: Path) -> StoryForge3Config:
    return StoryForge3Config(
        providers_config_dir=str(tmp_path / ".storyforge3"),
        default_model="test-model",
        books_dir=str(tmp_path / "books"),
    )


@pytest.fixture
def sample_chapter_text() -> str:
    paragraph = (
        "林默站在副楼门口，听见走廊尽头传来短促的提示音。"
        "他没有急着往前走，而是先把呼吸压稳，确认胸口那层熟悉的收敛感还在。"
        "护士从他身边经过，脚步停了一瞬，又像什么都没有发现一样继续向前。"
        "林默抬眼看向电子屏，B区号码正好跳到他的名字。"
        "下一秒，咨询室里传来医生压低的声音：先别进来。"
    )
    return "\n\n".join(f"{paragraph}{idx}" for idx in range(18))


@pytest.fixture
def mock_ccswitch_response() -> dict:
    return {
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "{\"ok\": true}"}],
            }
        ],
        "usage": {"input_tokens": 12, "output_tokens": 3},
        "model": "test-model",
    }


@pytest.fixture
def book_workspace(config: StoryForge3Config, sample_chapter_text: str) -> Path:
    root = Path(config.books_dir) / "lurenjia"
    (root / "chapters").mkdir(parents=True)
    (root / "context.md").write_text("主角林默，能力是存在感调节。", encoding="utf-8")
    (root / "chapters" / "0007.md").write_text(sample_chapter_text, encoding="utf-8")
    return root


def truth_payload() -> dict:
    return {
        "fact_assertions": ["林默继续在检测中心副楼接受异常咨询。"],
        "character_updates": [{"character_id": "lin_mo", "summary": "林默保持谨慎。"}],
        "relationship_updates": [],
        "hook_updates": [{"hook_id": "h1", "summary": "副楼异常仍未彻底结束。"}],
        "irreversible_facts": ["第8章发生在检测中心副楼。"],
        "notes": [],
    }


def response_text(text: str) -> dict:
    return {
        "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}],
        "usage": {"input_tokens": 5, "output_tokens": 8},
        "model": "test-model",
    }


def response_json(data: dict) -> dict:
    return response_text(json.dumps(data, ensure_ascii=False))
