from __future__ import annotations

from storyforge3.models import FanficMode, RuleSeverity


FANFIC_DIMENSIONS = [
    {
        "id": 34,
        "name": "角色还原度",
        "base_note": "检查角色的语癖、说话风格、行为模式是否与 fanfic_canon.md 角色档案一致。偏离必须有情境驱动。",
    },
    {
        "id": 35,
        "name": "世界规则遵守",
        "base_note": "检查章节内容是否违反 fanfic_canon.md 中的世界规则（地理、力量体系、阵营关系）。",
    },
    {
        "id": 36,
        "name": "关系动态",
        "base_note": "检查角色之间的关系互动是否合理，是否与 fanfic_canon.md 中标注的关键关系一致或有合理发展。",
    },
    {
        "id": 37,
        "name": "正典事件一致性",
        "base_note": "检查章节是否与 fanfic_canon.md 关键事件时间线矛盾。",
    },
]

SEVERITY_MAP: dict[FanficMode, dict[int, RuleSeverity]] = {
    FanficMode.CANON: {
        34: RuleSeverity.BLOCKING,
        35: RuleSeverity.BLOCKING,
        36: RuleSeverity.WARNING,
        37: RuleSeverity.BLOCKING,
    },
    FanficMode.AU: {
        34: RuleSeverity.BLOCKING,
        35: RuleSeverity.INFO,
        36: RuleSeverity.WARNING,
        37: RuleSeverity.INFO,
    },
    FanficMode.OOC: {
        34: RuleSeverity.INFO,
        35: RuleSeverity.WARNING,
        36: RuleSeverity.WARNING,
        37: RuleSeverity.INFO,
    },
    FanficMode.CP: {
        34: RuleSeverity.WARNING,
        35: RuleSeverity.WARNING,
        36: RuleSeverity.BLOCKING,
        37: RuleSeverity.INFO,
    },
}


def get_fanfic_dimension_config(mode: FanficMode) -> dict:
    """Return fanfiction-specific audit dimension config."""

    severity_map = SEVERITY_MAP[mode]
    notes: dict[int, str] = {}
    for dimension in FANFIC_DIMENSIONS:
        dimension_id = int(dimension["id"])
        severity = severity_map[dimension_id]
        if severity is RuleSeverity.BLOCKING:
            label = "（严格检查）"
        elif severity is RuleSeverity.INFO:
            label = "（仅记录，不判定失败）"
        else:
            label = "（警告级别）"
        notes[dimension_id] = f"{dimension['base_note']} {label}"
    return {
        "active_ids": [int(dimension["id"]) for dimension in FANFIC_DIMENSIONS],
        "severity_overrides": dict(severity_map),
        "deactivated_ids": [28, 29, 30, 31],
        "notes": notes,
    }
