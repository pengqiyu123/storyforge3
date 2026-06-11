from __future__ import annotations

import re

from storyforge3.models import FanficCanon, FanficMode


MODE_PREAMBLES = {
    FanficMode.CANON: """你正在写**原作向同人**。严格遵守正典：
- 角色的语癖、说话风格、行为模式必须与原作一致
- 世界规则不可违反
- 关键事件时间线不可矛盾
- 可以填充原作空白、探索未详述的角度""",
    FanficMode.AU: """你正在写**AU（平行世界）同人**：
- 世界规则可以改变（已在 allowedDeviations 中声明的偏离）
- 角色的核心性格和说话方式应保持辨识度——读者要能认出是谁
- AU 设定偏离必须内部一致（改了一条规则，相关的都要跟着变）""",
    FanficMode.OOC: """你正在写**OOC 同人**：
- 角色在极端情境下可以偏离性格底色
- 但偏离必须有情境驱动，不能无缘无故变性格
- 保留角色的语癖和说话特征——即使性格变了，说话方式也应有辨识度""",
    FanficMode.CP: """你正在写**CP 同人**，以角色互动和关系发展为核心：
- 配对双方每章必须有有效互动
- 互动风格要有化学反应——不是两个人在同一个场景各干各的
- 关系发展应有节奏感：推进、试探、阻碍、突破""",
}

MODE_CHECKS = {
    FanficMode.CANON: """- 正典合规检查：本章是否违反原作设定？角色对话是否符合原作语癖？
- 信息边界检查：角色是否引用了不该知道的信息？""",
    FanficMode.AU: """- AU 偏离清单：本章改变了哪些世界规则？改变是否内部一致？
- 角色辨识度检查：读者能否从对话中认出角色？""",
    FanficMode.OOC: """- OOC 偏离记录：角色在哪些方面偏离了性格底色？偏离驱动力是什么？
- 语癖保留检查：即使 OOC，说话方式是否还有原作特征？""",
    FanficMode.CP: """- CP 互动检查：配对双方本章是否有有效互动？关系发展是否推进？
- 互动质量检查：互动是否有化学反应（不是各干各的）？""",
}


def build_fanfic_canon_section(canon: FanficCanon) -> str:
    """Build the canon reference block injected into drafting context."""

    return f"""
## 同人正典参照

{MODE_PREAMBLES[canon.mode]}

以下是原作正典信息，写作时必须参照：

{canon.full_document}""".strip()


def build_character_voice_profiles(fanfic_canon: str) -> str:
    """Extract character voice hints from the canon markdown table."""

    table_match = re.search(
        r"## 角色档案[\s\S]*?\n(\|[^\n]+\|\n\|[-|\s]+\|\n(?:\|[^\n]+\|\n?)*)",
        fanfic_canon,
    )
    if not table_match:
        return ""
    rows = []
    for line in table_match.group(1).splitlines():
        if not line.startswith("|") or line.startswith("|--") or line.startswith("| 角色"):
            continue
        cells = [cell.strip() for cell in line.split("|") if cell.strip()]
        if len(cells) >= 6:
            rows.append(cells)
    if not rows:
        return ""
    profiles = []
    for cells in rows:
        name, _, _, catchphrases, speaking_style, behavior = cells[:6]
        parts = [f"### {name}"]
        if catchphrases and catchphrases != "（素材未提及）":
            parts.append(f"- 口头禅/语癖：{catchphrases}")
        if speaking_style and speaking_style != "（素材未提及）":
            parts.append(f"- 说话风格：{speaking_style}")
        if behavior and behavior != "（素材未提及）":
            parts.append(f"- 典型行为：{behavior}")
        profiles.append("\n".join(parts))
    return f"""
## 角色语音参照（同人写作专用）

以下角色的对话和行为必须参照原作特征。写对话时，先想"这个角色在原作里会怎么说"。

{chr(10).join(profiles)}""".strip()


def build_fanfic_mode_instructions(mode: FanficMode, allowed_deviations: tuple[str, ...] = ()) -> str:
    """Build fanfiction-specific self-check instructions."""

    deviations_block = ""
    if allowed_deviations:
        deviations = "\n".join(f"- {item}" for item in allowed_deviations)
        deviations_block = f"\n允许的偏离（不视为违规）：\n{deviations}\n"
    return f"""
## 同人写作自检（在 PRE_WRITE_CHECK 中额外检查）

{MODE_CHECKS[mode]}{deviations_block}""".strip()
