# Codex 指令：Phase 6C — 同人模式（Canon 导入 + 模式审计 + 提示注入）

> 发出日期：2026-06-09
> 产品经理：Claude Code PM
> 执行者：Codex
> 前置条件：Phase 6D-2 完成（335 后端 tests, 34 前端 tests, 4 Rust tests, ruff/cargo clean）

---

## 任务概述

为 StoryForge3 添加同人小说创作模式。同人模式的核心是：**从原作文本中提取结构化正典（canon），注入到写作和审计流程中，确保同人作品在角色语音、世界规则、事件时间线上与原作保持一致。**

三个交付物：

1. **Canon 导入服务** — LLM 从原作文本提取世界规则、角色档案、事件时间线、力量体系、写作风格
2. **同人审计维度** — 4 个新的 LLM 审计维度（角色还原度/世界规则/关系动态/正典一致性），按模式调整严重级别
3. **提示注入** — 写作时注入 canon 上下文 + 模式约束，确保生成的章节遵循同人规则

**核心原则**：InkOS 的提示模板和 section 解析逻辑是语言无关的字符串处理，直接移植到 Python。severity 映射表是纯数据，直接复制。

---

## InkOS 借鉴来源

| InkOS 文件 | 行数 | 借鉴方式 |
|-----------|------|----------|
| `fanfic-canon-importer.ts` | 146 | 提示模板（~90 行 systemPrompt）直接复制为 Python 字符串；section 解析逻辑移植为 Python 正则 |
| `fanfic-dimensions.ts` | 88 | severity 映射表直接复制为 Python dict；维度定义复制为 list[dict] |
| `fanfic-prompt-sections.ts` | 110 | MODE_PREAMBLES / MODE_CHECKS / buildCharacterVoiceProfiles() 移植为 Python 函数 |
| `fanfic.ts`（CLI） | 183 | 参考 init/show/refresh 命令模式，不直接移植 |

**InkOS 文件位置**：`storyforge/process/inkos-master (2)/inkos-master/packages/core/src/agents/`

---

## 数据模型

### 新增模型（`models.py`）

```python
class FanficMode(str, Enum):
    """同人创作模式。"""
    CANON = "canon"      # 原作向：严格遵守原作设定
    AU = "au"            # 平行世界：世界规则可改，角色保留
    OOC = "ooc"          # 角色可偏离：极端情境下允许性格偏离
    CP = "cp"            # 配对关系：以角色互动为核心

@dataclass(frozen=True)
class FanficCanon:
    """从原作提取的结构化正典。"""
    book_id: str
    source_name: str          # 原作名称
    mode: FanficMode
    world_rules: str          # 世界规则
    character_profiles: str   # 角色档案（Markdown 表格）
    key_events: str           # 关键事件时间线（Markdown 表格）
    power_system: str         # 力量体系
    writing_style: str        # 原作写作风格
    full_document: str        # 完整 Markdown 文档
    generated_at: str = ""    # ISO 时间戳
```

### 修改现有模型

**`BookMeta`** 添加 `fanfic_mode` 字段：

```python
@dataclass(frozen=True)
class BookMeta:
    # ... 现有字段不变 ...
    fanfic_mode: str = ""  # 空=原创，"canon"/"au"/"ooc"/"cp"=同人模式
```

**不修改 `Character` 模型**。同人角色档案存在 `FanficCanon.character_profiles` 中作为只读参考，不混入 SF3 自己的角色模型。

### 存储

- `books/{id}/fanfic_canon.md` — 人类可读的完整正典文档
- `books/{id}/fanfic_canon.json` — 机器可读的结构化数据（`FanficCanon` 序列化）

---

## 功能 1：Canon 导入服务

### 新增文件

#### 1.1 `src/storyforge3/services/fanfic_service.py`（新建，~120 行）

```python
from storyforge3.models import FanficCanon, FanficMode

class FanficService:
    """同人正典导入与管理。"""

    CANON_IMPORTER_PROMPT = """
你是一个专业的同人创作素材分析师。你的任务是从用户提供的原作素材中提取结构化正典信息，供同人写作系统使用。

同人模式：{mode_label}

你需要从原作素材中提取以下内容，每个部分用 === SECTION: <name> === 分隔：

=== SECTION: world_rules ===
世界规则（地理、物理法则、魔法/力量体系、阵营组织、社会结构）。
如果原作素材不包含明确的世界规则，从已有信息合理推断。

=== SECTION: character_profiles ===
角色档案表格，每个重要角色一行：

| 角色 | 身份 | 性格底色 | 语癖/口头禅 | 说话风格 | 行为模式 | 关键关系 | 信息边界 |
|------|------|----------|-------------|----------|----------|----------|----------|

要求：
- 语癖/口头禅必须从原文中精确提取，如有的话
- 说话风格描述该角色的语气、用词偏好、句式特征
- 行为模式描述该角色在特定情境下的典型反应
- 信息边界标注该角色知道什么、不知道什么
- 至少提取 3 个角色，不超过 15 个

=== SECTION: key_events ===
关键事件时间线：

| 序号 | 事件 | 涉及角色 | 对同人写作的约束 |
|------|------|----------|------------------|

按时间/出现顺序排列，标注每个事件对同人创作的约束程度。

=== SECTION: power_system ===
力量/能力体系（如果适用）。包括等级划分、核心规则、已知限制。
如果原作没有明确的力量体系，输出"（原作无明确力量体系）"。

=== SECTION: writing_style ===
原作写作风格特征（供同人写作模仿）：

1. 叙事人称与视角（第一人称/第三人称有限/全知，是否频繁切换）
2. 句式节奏（长短句交替模式、段落平均长度感受、对话占比）
3. 场景描写手法（五感偏好、意象选择、环境描写密度）
4. 对话标记习惯（说/道/笑道 等用法，对话前后是否有动作/表情补充）
5. 情绪表达方式（直白内心独白 vs 动作外化 vs 环境映射）
6. 比喻/修辞倾向（常用比喻类型、修辞频率）
7. 节奏转换（紧张→舒缓的过渡方式、章节结尾习惯）

每项用1-2个原文例句佐证。只提取原文实际存在的特征，不要泛泛描述。

提取原则：
- 忠实于原作素材，不捏造原作中没有的信息
- 信息不足时标注"（素材未提及）"而非编造
- 角色语癖是最重要的字段——同人读者最在意角色"像不像"
- 写作风格提取必须基于实际文本特征，附原文例句
{truncation_note}
"""
    # ↑ 以上提示模板直接从 InkOS fanfic-canon-importer.ts 移植

    MODE_LABELS = {
        FanficMode.CANON: "原作向（严格遵守原作设定）",
        FanficMode.AU: "AU/平行世界（世界规则可改，角色保留）",
        FanficMode.OOC: "OOC（角色性格可偏离原作）",
        FanficMode.CP: "CP（以配对关系为核心）",
    }

    MAX_SOURCE_LENGTH = 50_000  # 50k 字符上限，与 InkOS 一致

    def __init__(self, llm: Any, config: StoryForge3Config) -> None:
        self.llm = llm
        self.config = config

    async def import_canon(
        self,
        book_id: str,
        source_text: str,
        source_name: str,
        mode: FanficMode,
    ) -> FanficCanon:
        """从原作文本提取结构化正典。"""
        ...

    async def refresh_canon(
        self,
        book_id: str,
        source_text: str,
    ) -> FanficCanon:
        """用更新后的源文本重新提取正典（保持原模式）。"""
        ...

    def get_canon(self, book_id: str) -> FanficCanon | None:
        """读取已导入的正典。"""
        ...

    def _parse_sections(self, response: str) -> dict[str, str]:
        """从 LLM 响应中提取各 section。直接移植 InkOS 的正则逻辑。"""
        ...

    def _build_full_document(
        self,
        source_name: str,
        mode: FanficMode,
        sections: dict[str, str],
    ) -> str:
        """组装完整 Markdown 文档。移植 InkOS 的 fullDocument 组装逻辑。"""
        ...

    def _save_canon(self, book_id: str, canon: FanficCanon) -> None:
        """持久化到 fanfic_canon.md + fanfic_canon.json。"""
        ...
```

**关键实现细节**：

1. `_parse_sections()` 用正则 `=== SECTION: (\w+) ===\s*([\s\S]*?)(?==== SECTION:|$)` 提取，与 InkOS 完全一致
2. `import_canon()` 调用 `self.llm.generate()` 发送提示，temperature=0.3（与 InkOS 一致）
3. 截断逻辑：超过 50k 字符时截断，提示中附加 `注意：原作素材过长，已截断。请基于已有部分提取。`
4. 存储为两个文件：`.md`（人类可读）+ `.json`（机器可读）

### Service Protocol

#### 1.2 `src/storyforge3/services/protocols.py` — 新增 Protocol

```python
class FanficServiceProtocol(Protocol):
    """Fanfiction canon import and management."""

    async def import_canon(
        self, book_id: str, source_text: str, source_name: str, mode: FanficMode,
    ) -> FanficCanon: ...

    async def refresh_canon(
        self, book_id: str, source_text: str,
    ) -> FanficCanon: ...

    def get_canon(self, book_id: str) -> FanficCanon | None: ...
```

### API 路由

#### 1.3 `src/storyforge3/api/routes/fanfic.py`（新建，~80 行）

```python
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/api/books/{book_id}/fanfic", tags=["fanfic"])

class CanonImportRequest(BaseModel):
    source_text: str
    source_name: str
    mode: str  # "canon" | "au" | "ooc" | "cp"

@router.post("/import")
async def import_canon(book_id: str, request: CanonImportRequest, ...): ...

@router.get("/canon")
async def get_canon(book_id: str, ...): ...

@router.post("/refresh")
async def refresh_canon(book_id: str, request: CanonImportRequest, ...): ...
```

#### 1.4 `src/storyforge3/api/app.py` — 注册路由

在现有路由注册之后添加 `fanfic` 路由。

---

## 功能 2：同人审计维度

### 2.1 `src/storyforge3/fanfic/dimensions.py`（新建，~60 行）

**直接移植 InkOS `fanfic-dimensions.ts`**。

```python
from storyforge3.models import FanficMode, RuleSeverity

# 同人专用审计维度
FANFIC_DIMENSIONS = [
    {"id": 34, "name": "角色还原度", "base_note": "检查角色的语癖、说话风格、行为模式是否与 canon 角色档案一致。偏离必须有情境驱动。"},
    {"id": 35, "name": "世界规则遵守", "base_note": "检查章节内容是否违反 canon 中的世界规则（地理、力量体系、阵营关系）。"},
    {"id": 36, "name": "关系动态", "base_note": "检查角色之间的关系互动是否合理，是否与 canon 中标注的关键关系一致或有合理发展。"},
    {"id": 37, "name": "正典事件一致性", "base_note": "检查章节是否与 canon 关键事件时间线矛盾。"},
]

# 模式 → 维度严重级别映射（直接复制 InkOS SEVERITY_MAP）
SEVERITY_MAP: dict[FanficMode, dict[int, RuleSeverity]] = {
    FanficMode.CANON: {34: RuleSeverity.BLOCKING, 35: RuleSeverity.BLOCKING, 36: RuleSeverity.WARNING, 37: RuleSeverity.BLOCKING},
    FanficMode.AU:    {34: RuleSeverity.BLOCKING, 35: RuleSeverity.INFO,     36: RuleSeverity.WARNING, 37: RuleSeverity.INFO},
    FanficMode.OOC:   {34: RuleSeverity.INFO,     35: RuleSeverity.WARNING,  36: RuleSeverity.WARNING, 37: RuleSeverity.INFO},
    FanficMode.CP:    {34: RuleSeverity.WARNING,  35: RuleSeverity.WARNING,  36: RuleSeverity.BLOCKING, 37: RuleSeverity.INFO},
}

def get_fanfic_dimension_config(mode: FanficMode) -> dict:
    """返回同人模式下的审计维度配置。"""
    ...
```

### 2.2 修改 `AuditService` — 条件注入同人维度

当书的 `fanfic_mode` 非空时，`run_llm_audit()` 额外检查 4 个同人维度。**不修改 `run_mechanical()`**（36 条机械规则与同人无关），只在 LLM 审计层面加入同人检查。

在 `audit_service.py` 的 `run_llm_audit()` 中：

```python
async def run_llm_audit(self, text: str, context: str, *, model: str | None = None, book_id: str | None = None) -> LLMAuditResult:
    # ... 现有逻辑 ...
    fanfic_mode = self._get_fanfic_mode(book_id)
    if fanfic_mode:
        fanfic_context = self._build_fanfic_audit_context(book_id, fanfic_mode)
        context = context + "\n\n" + fanfic_context
    # ... 继续 LLM 调用 ...
```

---

## 功能 3：提示注入

### 3.1 `src/storyforge3/fanfic/prompt_sections.py`（新建，~90 行）

**直接移植 InkOS `fanfic-prompt-sections.ts`**。

```python
from storyforge3.models import FanficMode

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
    """构建注入到写作提示中的 canon 参照段落。"""
    ...

def build_character_voice_profiles(character_profiles: str) -> str:
    """从角色档案表格提取语音参照。移植 InkOS 的 table 解析逻辑。"""
    ...

def build_fanfic_mode_instructions(mode: FanficMode, allowed_deviations: tuple[str, ...] = ()) -> str:
    """构建同人写作自检指令。"""
    ...
```

### 3.2 修改 `ChapterService` — 写作时注入 canon

在 `chapter_service.py` 的 draft 方法中，当书的 `fanfic_mode` 非空时：

1. 读取 `fanfic_canon.json`
2. 调用 `build_fanfic_canon_section()` 和 `build_character_voice_profiles()`
3. 附加到 context payload 中

**不修改 draft 的核心流程**，只在 context 构建阶段追加同人信息。

### 3.3 修改 `BookService` — 创建书籍时支持 fanfic_mode

在 `BookMeta` 创建时，如果请求包含 `fanfic_mode` 字段，保存到 book.json。

---

## 文件改动清单

### 后端新增（~350 行）

| 文件 | 操作 | 行数 | 说明 |
|------|------|------|------|
| `src/storyforge3/models.py` | 修改 | +25 | 新增 `FanficMode` enum + `FanficCanon` dataclass + `BookMeta.fanfic_mode` 字段 |
| `src/storyforge3/fanfic/__init__.py` | 新建 | +3 | 模块导出 |
| `src/storyforge3/fanfic/dimensions.py` | 新建 | +60 | 从 InkOS `fanfic-dimensions.ts` 移植 |
| `src/storyforge3/fanfic/prompt_sections.py` | 新建 | +90 | 从 InkOS `fanfic-prompt-sections.ts` 移植 |
| `src/storyforge3/services/fanfic_service.py` | 新建 | +120 | Canon 导入服务（提示模板 + section 解析 + 持久化） |
| `src/storyforge3/services/protocols.py` | 修改 | +10 | 新增 `FanficServiceProtocol` |
| `src/storyforge3/api/routes/fanfic.py` | 新建 | +80 | 3 个 API 端点 |
| `src/storyforge3/api/app.py` | 修改 | +2 | 注册 fanfic 路由 |
| `src/storyforge3/services/book_service.py` | 修改 | +5 | 创建书籍时保存 fanfic_mode |
| `src/storyforge3/services/chapter_service.py` | 修改 | +10 | draft 时注入 canon context |
| `src/storyforge3/services/audit_service.py` | 修改 | +8 | LLM 审计时注入同人维度 |
| `src/storyforge3/services/deps.py` | 修改 | +3 | 注入 FanficService |

### 后端测试新增（~200 行）

| 文件 | 说明 |
|------|------|
| `tests/test_fanfic_service.py` | Canon 导入 + section 解析 + 持久化（~80 行） |
| `tests/test_fanfic_dimensions.py` | 维度配置 + severity 映射（~40 行） |
| `tests/test_fanfic_prompt_sections.py` | 提示构建 + 角色语音提取（~50 行） |
| `tests/test_api_fanfic.py` | API 端点集成测试（~30 行） |

### 前端

**本阶段不涉及前端改动。** Canon 导入通过 API 调用，前端展示留到后续阶段。理由：先验证后端同人流程正确，前端 UI 可以之后补。

---

## 借鉴细节

### 从 InkOS 直接移植的代码

#### 提示模板（`fanfic-canon-importer.ts:37-90`）

InkOS 的 systemPrompt 是 ~54 行纯文本。移植方式：复制为 Python 三引号字符串，用 `{mode_label}` 和 `{truncation_note}` 占位符。**零修改**。

#### Section 解析（`fanfic-canon-importer.ts:101-107`）

```typescript
const extract = (tag: string): string => {
  const regex = new RegExp(`=== SECTION: ${tag} ===\\s*([\\s\\S]*?)(?==== SECTION:|$)`);
  const match = content.match(regex);
  return match?.[1]?.trim() ?? "";
};
```

移植为 Python：
```python
def _parse_sections(self, response: str) -> dict[str, str]:
    pattern = r"=== SECTION: (\w+) ===\s*([\s\S]*?)(?==== SECTION:|$)"
    result = {}
    for match in re.finditer(pattern, response):
        result[match.group(1)] = match.group(2).strip()
    return result
```

**改动**：从多次调用改为一次 `finditer`，更 Pythonic。正则逻辑不变。

#### Severity 映射（`fanfic-dimensions.ts:39-43`）

```typescript
const SEVERITY_MAP = {
  canon: { 34: "critical", 35: "critical", 36: "warning", 37: "critical" },
  au:    { 34: "critical", 35: "info",     36: "warning", 37: "info" },
  ooc:   { 34: "info",     35: "warning",  36: "warning", 37: "info" },
  cp:    { 34: "warning",  35: "warning",  36: "critical", 37: "info" },
};
```

移植为 Python dict，`"critical"` → `RuleSeverity.BLOCKING`（SF3 的命名惯例），其余逻辑不变。

#### Mode 前导文本（`fanfic-prompt-sections.ts:3-23`）

MODE_PREAMBLES 的 4 段文本直接复制，零修改。

#### Mode 自检项（`fanfic-prompt-sections.ts:83-95`）

MODE_CHECKS 的 4 段文本直接复制，零修改。

#### 角色语音提取（`fanfic-prompt-sections.ts:40-81`）

`buildCharacterVoiceProfiles()` 的表格解析逻辑移植为 Python。正则从 markdown 表格提取行，按 `|` 分割单元格。

### 不移植的 InkOS 代码

| 组件 | 原因 |
|------|------|
| `fanfic.ts` CLI 命令 | SF3 用 API 路由，不用 CLI |
| `FanficModeSchema` (zod) | SF3 用 Python enum |
| `FanficDimensionConfig` interface | SF3 用 dict，不需要 TypeScript interface |
| SPINOFF_DIMS [28-31] | InkOS 的外传维度，SF3 没有 |
| OOC_DIM (dim 1) 覆盖 | SF3 的 OOC 检查在 LLM 审计中，不在机械规则中 |

---

## 测试

### 后端

```powershell
cd storyforge3
.\.venv\Scripts\python.exe -m pytest tests/ -q   # 335+ tests 不退步
ruff check .
```

新增测试要点：

1. **`test_fanfic_service.py`**：
   - `test_parse_sections_extracts_all_five_sections` — 给定含 5 个 `=== SECTION: ===` 的文本，正确解析
   - `test_parse_sections_handles_missing_section` — 缺少某个 section 时返回空字符串
   - `test_import_canon_truncates_long_source` — 超过 50k 字符时截断
   - `test_import_canon_saves_md_and_json` — 持久化两个文件
   - `test_get_canon_returns_none_when_not_exists` — 未导入时返回 None
   - `test_refresh_canon_preserves_mode` — 刷新时保持原模式

2. **`test_fanfic_dimensions.py`**：
   - `test_canon_mode_has_blocking_on_34_35_37` — canon 模式 3 个 blocking
   - `test_au_mode_relaxes_world_rules` — AU 模式世界规则降级
   - `test_cp_mode_blocking_on_relationship` — CP 模式关系动态是 blocking
   - `test_ooc_mode_all_info_or_warning` — OOC 模式无 blocking

3. **`test_fanfic_prompt_sections.py`**：
   - `test_build_canon_section_includes_mode_preamble` — 包含模式前导文本
   - `test_build_voice_profiles_extracts_table_rows` — 从表格提取角色语音
   - `test_build_mode_instructions_includes_deviations` — 包含允许偏离列表

4. **`test_api_fanfic.py`**：
   - `test_import_canon_returns_200` — API 端点正常响应
   - `test_get_canon_returns_404_when_not_imported` — 未导入时 404
   - `test_invalid_mode_returns_422` — 无效模式被拒绝

### 前端

不涉及前端改动，34 个现有测试不应退步。

---

## 验收标准

### Canon 导入

- [ ] `POST /api/books/{id}/fanfic/import` 接受 source_text + source_name + mode
- [ ] LLM 提取的 canon 包含 5 个 section（world_rules / character_profiles / key_events / power_system / writing_style）
- [ ] 持久化为 `fanfic_canon.md`（人类可读）+ `fanfic_canon.json`（机器可读）
- [ ] 超过 50k 字符的源文本自动截断，提示中附加截断说明
- [ ] `GET /api/books/{id}/fanfic/canon` 返回已导入的正典
- [ ] `POST /api/books/{id}/fanfic/refresh` 可以重新导入

### 同人审计维度

- [ ] 4 个同人维度（34-37）定义正确
- [ ] canon 模式：角色还原度 + 世界规则 + 正典事件 = BLOCKING
- [ ] AU 模式：角色还原度 = BLOCKING，世界规则 = INFO
- [ ] OOC 模式：无 BLOCKING 维度
- [ ] CP 模式：关系动态 = BLOCKING
- [ ] 非同人书的审计流程完全不受影响

### 提示注入

- [ ] 同人书的 draft context 包含 canon 参照段落
- [ ] 同人书的 draft context 包含角色语音参照
- [ ] 同人书的 LLM 审计包含模式自检指令
- [ ] 非同人书的写作和审计流程完全不受影响

### 质量门

- [ ] pytest：335+ tests 全绿（新增 ~15 个）
- [ ] ruff check clean
- [ ] 前端 34 tests 不退步
- [ ] pnpm build 零错误

---

## 不在 6C 范围内

| 功能 | 归属 | 原因 |
|------|------|------|
| 同人模式前端 UI | 后续 | 先验证后端流程，UI 后补 |
| Canon 编辑器 | 后续 | 先支持导入，编辑能力后续加 |
| 多源导入 | 后续 | 目前只支持单文件 |
| 原作爬取集成 | 不做 | 用户自行准备原作文本 |
| 外传模式 | 不做 | InkOS 有但 SF3 不需要 |

---

## 参考文件

### 必须读取（借鉴来源）

1. **`storyforge/process/inkos-master (2)/inkos-master/packages/core/src/agents/fanfic-canon-importer.ts`** — 提示模板 + section 解析（146 行）
2. **`storyforge/process/inkos-master (2)/inkos-master/packages/core/src/agents/fanfic-dimensions.ts`** — 审计维度 + severity 映射（88 行）
3. **`storyforge/process/inkos-master (2)/inkos-master/packages/core/src/agents/fanfic-prompt-sections.ts`** — 模式前导文本 + 角色语音提取（110 行）

### 当前项目文件（需要修改）

4. **`src/storyforge3/models.py`** — 新增 FanficMode + FanficCanon + BookMeta.fanfic_mode
5. **`src/storyforge3/services/protocols.py`** — 新增 FanficServiceProtocol
6. **`src/storyforge3/services/book_service.py`** — 创建书籍时保存 fanfic_mode
7. **`src/storyforge3/services/chapter_service.py`** — draft 时注入 canon context
8. **`src/storyforge3/services/audit_service.py`** — LLM 审计时注入同人维度
9. **`src/storyforge3/services/deps.py`** — 注入 FanficService
10. **`src/storyforge3/api/app.py`** — 注册 fanfic 路由

### 需要参考的测试文件

11. **`tests/test_api_books.py`** — 参考 API 测试模式
12. **`tests/test_services.py`** — 参考 service 测试模式

---

## 完成后回报格式

```
给 ClaudeCode 产品经理的执行结果：

Phase 6C（同人模式）：

功能 1 — Canon 导入：
- FanficService：[状态 + 行数]
- 提示模板：[状态 + 是否从 InkOS 移植]
- Section 解析：[状态]
- 持久化（md + json）：[状态]
- API 路由：[状态 + 端点数]

功能 2 — 同人审计维度：
- dimensions.py：[状态 + 行数]
- severity 映射：[状态]
- AuditService 集成：[状态]

功能 3 — 提示注入：
- prompt_sections.py：[状态 + 行数]
- ChapterService 集成：[状态]
- 非同人书不受影响：[验证方式]

测试：
- 新增测试：[数量] passed
- 后端全量：[数量] passed
- ruff check：[状态]
- 前端：[数量] passed
- pnpm build：[状态]

改动文件列表：[...]
```
