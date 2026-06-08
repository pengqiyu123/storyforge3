from __future__ import annotations

from storyforge3.style.contract import StyleContract


class StyleCompiler:
    def compile_prompt_fragment(self, contract: StyleContract) -> str:
        parts = [
            f"[STYLE: {contract.display_name} v{contract.version}]",
            f"对话占比目标：{contract.dialogue_density[0]:.0%}-{contract.dialogue_density[1]:.0%}",
            f"叙事占比目标：{contract.narration_ratio[0]:.0%}-{contract.narration_ratio[1]:.0%}",
            f"句长目标：{contract.sentence_length_range[0]}-{contract.sentence_length_range[1]} 字",
        ]
        if contract.required_traits:
            parts.append("必要风格：" + "；".join(contract.required_traits))
        if contract.banned_phrases:
            parts.append("禁用短语：" + "、".join(contract.banned_phrases))
        if contract.fatigue_words:
            parts.append("疲劳词限量：" + "、".join(contract.fatigue_words))
        if contract.prompt_extra.strip():
            parts.append("补充：" + contract.prompt_extra.strip())
        return "\n".join(parts)

    def compile_forbidden_terms(self, contract: StyleContract) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*contract.banned_phrases, *contract.fatigue_words)))
