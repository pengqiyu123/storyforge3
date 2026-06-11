"""Fanfiction mode helpers."""

from storyforge3.fanfic.dimensions import FANFIC_DIMENSIONS, get_fanfic_dimension_config
from storyforge3.fanfic.prompt_sections import (
    build_character_voice_profiles,
    build_fanfic_canon_section,
    build_fanfic_mode_instructions,
)

__all__ = [
    "FANFIC_DIMENSIONS",
    "build_character_voice_profiles",
    "build_fanfic_canon_section",
    "build_fanfic_mode_instructions",
    "get_fanfic_dimension_config",
]
