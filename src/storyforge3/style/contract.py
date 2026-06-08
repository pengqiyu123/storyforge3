from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StyleContract:
    contract_id: str
    display_name: str
    dialogue_density: tuple[float, float] = (0.2, 0.45)
    narration_ratio: tuple[float, float] = (0.35, 0.8)
    sentence_length_range: tuple[int, int] = (8, 45)
    banned_phrases: tuple[str, ...] = ()
    fatigue_words: tuple[str, ...] = ()
    required_traits: tuple[str, ...] = ()
    description: str = ""
    version: int = 1
    prompt_extra: str = ""
    character_voice_hints: dict[str, tuple[str, ...]] = field(default_factory=dict)


DEFAULT_STYLE_CONTRACT = StyleContract(
    contract_id="default-web-novel-v1",
    display_name="默认网文风格",
    description="中文网文通用风格基线。",
    banned_phrases=("本章", "下一章", "修订稿", "剧情"),
    fatigue_words=("突然", "一股", "原来如此", "心头一震"),
    required_traits=("对话与叙事交替推进", "比喻贴场景不贴情绪", "句长变化有节奏"),
)


LURENJIA_STYLE_CONTRACT = StyleContract(
    contract_id="lurenjia-v1",
    display_name="我是路人甲风格",
    dialogue_density=(0.2, 0.38),
    narration_ratio=(0.4, 0.78),
    sentence_length_range=(7, 42),
    banned_phrases=("本章", "下一章", "修订稿", "剧情", "这一章必须"),
    fatigue_words=("突然", "一股", "原来如此", "心头一震", "瞳孔一缩"),
    required_traits=("存在感系统", "都市玄幻悬疑", "推理必须有可观察线索", "主角内声自然口语"),
    prompt_extra="每章至少推进一个检测中心、系统熟练度或存在感异常相关线索。",
)
