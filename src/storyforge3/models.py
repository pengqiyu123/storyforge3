from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


# ── Chapter lifecycle ───────────────────────────────────────


class ChapterStatus(str, Enum):
    """Chapter lifecycle state."""

    EMPTY = "empty"
    PLANNED = "planned"
    DRAFTED = "drafted"
    SETTLED = "settled"
    AUDITED = "audited"
    NEEDS_REVISION = "needs_revision"
    REVISED = "revised"
    APPROVED = "approved"
    EXPORTED = "exported"
    NEEDS_REVIEW = "needs_review"


class RuleSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"


class RuleCategory(str, Enum):
    INTEGRITY = "integrity"
    AI_TELL = "ai_tell"
    STYLE = "style"
    STRUCTURE = "structure"
    META = "meta"


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    passed: bool
    severity: RuleSeverity
    category: RuleCategory
    message: str
    detail: dict = field(default_factory=dict)


@dataclass(frozen=True)
class AuditResult:
    chapter_no: int
    passed: bool
    blocking_issues: tuple[str, ...]
    warnings: tuple[str, ...]
    info: tuple[str, ...]
    rule_results: tuple[RuleResult, ...]


@dataclass(frozen=True)
class TruthData:
    chapter_no: int
    source: str
    fact_assertions: tuple[str, ...]
    character_updates: tuple[dict, ...]
    relationship_updates: tuple[dict, ...]
    hook_updates: tuple[dict, ...]
    irreversible_facts: tuple[str, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True)
class LLMCallRecord:
    """Audit record for one LLM call."""

    task_name: str
    model: str
    prompt_version: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: float
    success: bool
    error: str | None = None


@dataclass(frozen=True)
class ChapterResult:
    """Immutable result for one chapter run."""

    book_id: str
    chapter_no: int
    status: ChapterStatus
    title: str
    text: str
    audit: AuditResult | None = None
    truth: TruthData | None = None
    llm_calls: tuple[LLMCallRecord, ...] = ()
    error: str | None = None


# ── Book & creation models ──────────────────────────────────


class BookStatus(str, Enum):
    INCUBATING = "incubating"
    OUTLINING = "outlining"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    DROPPED = "dropped"


@dataclass(frozen=True)
class BookConfig:
    """Parameters for creating a new book."""

    title: str
    genre: str  # xuanhuan, xianxia, urban, horror, other
    platform: str  # tomato, feilu, qidian, other
    target_chapters: int
    chapter_word_count: int  # target words per chapter
    language: str = "zh"


@dataclass(frozen=True)
class BookMeta:
    """Persisted book metadata."""

    book_id: str
    title: str
    genre: str
    platform: str
    status: BookStatus
    target_chapters: int
    chapter_word_count: int
    language: str = "zh"
    current_chapter: int = 0
    created_at: str = ""
    updated_at: str = ""
    style_fingerprint: dict | None = None


# ── World building ──────────────────────────────────────────


@dataclass(frozen=True)
class WorldConfig:
    """Generated world configuration."""

    book_id: str
    setting: str  # 世界观描述
    power_system: str  # 力量体系
    core_conflict: str  # 核心冲突
    rules: tuple[str, ...] = ()  # 基本规则列表


# ── Character ───────────────────────────────────────────────


class CharacterRole(str, Enum):
    PROTAGONIST = "protagonist"
    MAJOR = "major"
    MINOR = "minor"


@dataclass(frozen=True)
class Character:
    """A character in the book."""

    book_id: str
    name: str
    role: CharacterRole
    profile: str  # 角色档案
    personality: str  # 性格特征
    abilities: tuple[str, ...] = ()
    arc_direction: str = ""  # 角色弧线方向


@dataclass(frozen=True)
class Relationship:
    """Relationship between two characters."""

    character_a: str
    character_b: str
    relation_type: str  # ally, rival, mentor, family, love, etc.
    description: str


# ── Volume outline ──────────────────────────────────────────


@dataclass(frozen=True)
class VolumeOutline:
    """A volume's structure and pacing plan."""

    book_id: str
    volume_no: int
    title: str
    chapter_count: int
    synopsis: str  # 卷概要
    key_scenes: tuple[str, ...] = ()  # 关键场景描述
    rhythm_curve: tuple[str, ...] = ()  # 每章节奏标记 (rise/peak/fall/rest)


# ── Chapter plan (intent) ───────────────────────────────────


@dataclass(frozen=True)
class ChapterIntent:
    """Chapter planning intent generated before drafting."""

    chapter_no: int
    goal: str  # 本章目标 (max 50 chars)
    outline_node: str = ""  # 对应卷纲节点
    arc_context: str = ""  # 角色弧线上下文
    must_keep: tuple[str, ...] = ()  # 必须保留
    must_avoid: tuple[str, ...] = ()  # 必须避免
    style_emphasis: tuple[str, ...] = ()  # 风格侧重
