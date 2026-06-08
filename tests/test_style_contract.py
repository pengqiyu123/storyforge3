from __future__ import annotations

from storyforge3.style.compiler import StyleCompiler
from storyforge3.style.contract import DEFAULT_STYLE_CONTRACT, LURENJIA_STYLE_CONTRACT, StyleContract


def test_style_contract_is_frozen() -> None:
    contract = StyleContract(contract_id="x", display_name="X")
    try:
        contract.display_name = "Y"  # type: ignore[misc]
    except Exception as exc:
        assert exc.__class__.__name__ == "FrozenInstanceError"
    else:
        raise AssertionError("StyleContract should be frozen")


def test_default_style_contract_has_required_dimensions() -> None:
    contract = DEFAULT_STYLE_CONTRACT
    assert contract.dialogue_density == (0.2, 0.45)
    assert contract.narration_ratio == (0.35, 0.8)
    assert contract.sentence_length_range == (8, 45)
    assert "本章" in contract.banned_phrases
    assert "突然" in contract.fatigue_words


def test_lurenjia_contract_is_stricter_than_default() -> None:
    assert LURENJIA_STYLE_CONTRACT.dialogue_density[1] < DEFAULT_STYLE_CONTRACT.dialogue_density[1]
    assert "存在感系统" in LURENJIA_STYLE_CONTRACT.required_traits


def test_style_compiler_builds_prompt_constraints() -> None:
    rendered = StyleCompiler().compile_prompt_fragment(LURENJIA_STYLE_CONTRACT)
    assert "对话占比" in rendered
    assert "禁用短语" in rendered
    assert "存在感系统" in rendered
