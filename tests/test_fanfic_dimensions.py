from __future__ import annotations

from storyforge3.fanfic.dimensions import FANFIC_DIMENSIONS, get_fanfic_dimension_config
from storyforge3.models import FanficMode, RuleSeverity


def test_fanfic_dimensions_define_34_to_37() -> None:
    assert [item["id"] for item in FANFIC_DIMENSIONS] == [34, 35, 36, 37]
    assert [item["name"] for item in FANFIC_DIMENSIONS] == ["角色还原度", "世界规则遵守", "关系动态", "正典事件一致性"]


def test_canon_mode_has_blocking_on_34_35_37() -> None:
    config = get_fanfic_dimension_config(FanficMode.CANON)

    assert config["active_ids"] == [34, 35, 36, 37]
    assert config["severity_overrides"][34] == RuleSeverity.BLOCKING
    assert config["severity_overrides"][35] == RuleSeverity.BLOCKING
    assert config["severity_overrides"][36] == RuleSeverity.WARNING
    assert config["severity_overrides"][37] == RuleSeverity.BLOCKING
    assert "严格检查" in config["notes"][34]


def test_au_mode_relaxes_world_rules() -> None:
    config = get_fanfic_dimension_config(FanficMode.AU)

    assert config["severity_overrides"][34] == RuleSeverity.BLOCKING
    assert config["severity_overrides"][35] == RuleSeverity.INFO
    assert config["severity_overrides"][37] == RuleSeverity.INFO


def test_cp_mode_blocks_relationship_dimension() -> None:
    config = get_fanfic_dimension_config(FanficMode.CP)

    assert config["severity_overrides"][36] == RuleSeverity.BLOCKING
    assert config["severity_overrides"][34] == RuleSeverity.WARNING


def test_ooc_mode_has_no_blocking_dimensions() -> None:
    config = get_fanfic_dimension_config(FanficMode.OOC)

    assert RuleSeverity.BLOCKING not in set(config["severity_overrides"].values())
    assert "仅记录" in config["notes"][34]
