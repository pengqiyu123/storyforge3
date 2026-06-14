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
    TRUTH_COMMITTED = "truth_committed"
    EXPORTED = "exported"
    NEEDS_REVIEW = "needs_review"


class RunStatus(str, Enum):
    """Lifecycle state for one pipeline run instance."""

    PENDING = "pending"
    RUNNING = "running"
    WAITING_FOR_HUMAN = "waiting_for_human"
    COMPLETED = "completed"
    FAILED = "failed"
    RESUMABLE = "resumable"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class StageResult:
    """Persisted result for one stage within a pipeline run."""

    stage: str
    status: str
    started_at: str
    finished_at: str | None = None
    duration_ms: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    summary: dict | None = None


@dataclass(frozen=True)
class PipelineRunRecord:
    """Queryable current-state record for one pipeline run."""

    run_id: str
    book_id: str
    chapter_no: int
    mode: str
    target_stages: list[str]
    status: RunStatus
    current_stage: str | None
    started_at: str
    updated_at: str
    stage_results: dict[str, StageResult] = field(default_factory=dict)
    llm_calls: list[dict] = field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    resume_from: str | None = None


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


class FanficMode(str, Enum):
    """Fanfiction writing mode."""

    CANON = "canon"
    AU = "au"
    OOC = "ooc"
    CP = "cp"


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
class RevisionDiffBlock:
    kind: str
    before_text: str = ""
    after_text: str = ""


@dataclass(frozen=True)
class RevisionDiffSummary:
    changed_blocks: int
    added_blocks: int
    removed_blocks: int
    before_chars: int
    after_chars: int


@dataclass(frozen=True)
class RevisionDiff:
    unit: str
    summary: RevisionDiffSummary
    blocks: tuple[RevisionDiffBlock, ...]


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
    revision_diff: RevisionDiff | None = None
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
    fanfic_mode: str = ""


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
    fanfic_mode: str = ""


@dataclass(frozen=True)
class FanficCanon:
    """Structured canon extracted from source material for fanfiction writing."""

    book_id: str
    source_name: str
    mode: FanficMode
    world_rules: str
    character_profiles: str
    key_events: str
    power_system: str
    writing_style: str
    full_document: str
    generated_at: str = ""


class ShortStoryStatus(str, Enum):
    """Short story lifecycle state."""

    EMPTY = "empty"
    PLANNED = "planned"
    DRAFTED = "drafted"
    AUDITED = "audited"
    REVISED = "revised"
    EXPORTED = "exported"


@dataclass(frozen=True)
class ShortStoryConfig:
    """Parameters for creating a short story."""

    title: str
    genre: str
    target_chars: int = 10_000
    premise: str = ""
    style: str = ""


@dataclass(frozen=True)
class ShortStoryMeta:
    """Persisted short story metadata."""

    book_id: str
    title: str
    genre: str
    status: ShortStoryStatus
    target_chars: int
    premise: str
    style: str
    actual_chars: int = 0
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class ShortStoryPlan:
    """Single-piece short story plan."""

    book_id: str
    premise: str
    opening: str = ""
    climax: str = ""
    ending: str = ""
    characters: str = ""
    key_scenes: tuple[str, ...] = ()
    must_keep: tuple[str, ...] = ()
    must_avoid: tuple[str, ...] = ()


@dataclass(frozen=True)
class ShortStoryResult:
    """Short story pipeline result."""

    book_id: str
    status: ShortStoryStatus
    text: str
    audit: AuditResult | None = None
    error: str | None = None


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


# ── Workspace management ───────────────────────────────────


@dataclass(frozen=True)
class WorkspaceValidation:
    valid: bool
    books_dir: str
    book_count: int
    issues: tuple[str, ...]


@dataclass(frozen=True)
class BackupResult:
    path: str
    book_count: int
    size_bytes: int
    created_at: str


@dataclass(frozen=True)
class RestoreResult:
    success: bool
    book_count: int
    backup_path: str
    message: str
