from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from storyforge3.audit.chinese_text import count_chinese_chars
from storyforge3.config import StoryForge3Config


@dataclass(frozen=True)
class LengthNormalizationResult:
    text: str
    action: str
    original_chars: int
    final_chars: int


class LengthNormalizer:
    def __init__(self, llm: Any, config: StoryForge3Config) -> None:
        self.llm = llm
        self.config = config

    async def normalize(
        self,
        text: str,
        *,
        target_chars: int,
        soft_ratio: float = 0.15,
        hard_range: tuple[int, int] | None = None,
    ) -> LengthNormalizationResult:
        original_chars = count_chinese_chars(text)
        soft_min = int(target_chars * (1 - soft_ratio))
        soft_max = int(target_chars * (1 + soft_ratio))
        hard_min, hard_max = hard_range or (int(target_chars * 0.7), int(target_chars * 1.4))
        if soft_min <= original_chars <= soft_max:
            return self._result(text, "none", original_chars)
        if hard_min <= original_chars <= hard_max:
            return self._result(text, "none", original_chars)
        action = "compress" if original_chars > hard_max else "expand"
        adjusted = await self.llm.generate_text(
            "length_normalize",
            self._prompt(action),
            {
                "action": action,
                "target_chars": target_chars,
                "hard_range": [hard_min, hard_max],
                "chapter_text": text,
                "instruction": "保留核心情节和事实，只调整长度。",
            },
            model=self.config.model_for_task("writer"),
            prompt_version="length-normalize-v1:v1",
        )
        return self._result(adjusted, action, original_chars)

    @staticmethod
    def _prompt(action: str) -> str:
        verb = "压缩" if action == "compress" else "扩写"
        return f"你是中文网文章节长度归一化编辑。请{verb}正文，保留核心情节、事实、角色行为和章节承接。只输出调整后的正文。"

    @staticmethod
    def _result(text: str, action: str, original_chars: int) -> LengthNormalizationResult:
        return LengthNormalizationResult(text=text, action=action, original_chars=original_chars, final_chars=count_chinese_chars(text))
