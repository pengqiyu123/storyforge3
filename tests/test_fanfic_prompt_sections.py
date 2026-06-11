from __future__ import annotations

from storyforge3.fanfic.prompt_sections import (
    build_character_voice_profiles,
    build_fanfic_canon_section,
    build_fanfic_mode_instructions,
)
from storyforge3.models import FanficCanon, FanficMode


CHARACTER_TABLE = """| 角色 | 身份 | 性格底色 | 语癖/口头禅 | 说话风格 | 行为模式 | 关键关系 | 信息边界 |
|------|------|----------|-------------|----------|----------|----------|----------|
| 林默 | 高三学生 | 谨慎 | 先等等 | 短句，先观察后回应 | 遇事先确认出口 | 与许青互相试探 | 不知道副楼真相 |
| 许青 | 记录员 | 冷静 | （素材未提及） | 用词克制，会先追问证据 | 先记录再行动 | 与林默互相试探 | 知道检测中心流程 |"""


def canon() -> FanficCanon:
    full_document = f"""# 同人正典（《原作A》）

## 世界规则
江城存在异常检测中心。

## 角色档案
{CHARACTER_TABLE}

## 关键事件时间线
林默进入检测中心。
"""
    return FanficCanon(
        book_id="book",
        source_name="原作A",
        mode=FanficMode.CANON,
        world_rules="江城存在异常检测中心。",
        character_profiles=CHARACTER_TABLE,
        key_events="林默进入检测中心。",
        power_system="存在感系统。",
        writing_style="短段落推进。",
        full_document=full_document,
    )


def test_build_canon_section_includes_mode_preamble() -> None:
    section = build_fanfic_canon_section(canon())

    assert "## 同人正典参照" in section
    assert "你正在写**原作向同人**" in section
    assert "角色的语癖、说话风格、行为模式必须与原作一致" in section
    assert "江城存在异常检测中心" in section


def test_build_voice_profiles_extracts_character_table_rows() -> None:
    section = build_character_voice_profiles(canon().full_document)

    assert "## 角色语音参照" in section
    assert "### 林默" in section
    assert "- 口头禅/语癖：先等等" in section
    assert "- 说话风格：短句，先观察后回应" in section
    assert "- 典型行为：遇事先确认出口" in section
    assert "### 许青" in section
    assert "口头禅/语癖：（素材未提及）" not in section


def test_build_voice_profiles_returns_empty_without_table() -> None:
    assert build_character_voice_profiles("## 角色档案\n无表格。") == ""


def test_build_mode_instructions_includes_deviations() -> None:
    section = build_fanfic_mode_instructions(FanficMode.AU, ("世界改为现代校园", "能力体系改为社团规则"))

    assert "## 同人写作自检" in section
    assert "AU 偏离清单" in section
    assert "允许的偏离" in section
    assert "- 世界改为现代校园" in section
    assert "- 能力体系改为社团规则" in section
