from __future__ import annotations

import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from storyforge3.config import StoryForge3Config
from storyforge3.models import FanficCanon, FanficMode
from storyforge3.storage import BookStorage, StoragePaths


class FanficService:
    """Fanfiction canon import and management."""

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
""".strip()

    MODE_LABELS = {
        FanficMode.CANON: "原作向（严格遵守原作设定）",
        FanficMode.AU: "AU/平行世界（世界规则可改，角色保留）",
        FanficMode.OOC: "OOC（角色性格可偏离原作）",
        FanficMode.CP: "CP（以配对关系为核心）",
    }
    MAX_SOURCE_LENGTH = 50_000
    SECTION_NAMES = ("world_rules", "character_profiles", "key_events", "power_system", "writing_style")

    def __init__(
        self,
        llm: Any,
        config: StoryForge3Config,
        *,
        storage: BookStorage | None = None,
        paths: StoragePaths | None = None,
    ) -> None:
        self.llm = llm
        self.config = config
        self.paths = paths or StoragePaths(Path(config.books_dir))
        self.storage = storage or BookStorage(self.paths.books_root)

    async def import_canon(
        self,
        book_id: str,
        source_text: str,
        source_name: str,
        mode: FanficMode,
    ) -> FanficCanon:
        """Extract and persist structured fanfiction canon from source text."""

        truncated = len(source_text) > self.MAX_SOURCE_LENGTH
        text = source_text[: self.MAX_SOURCE_LENGTH] if truncated else source_text
        truncation_note = "\n注意：原作素材过长，已截断。请基于已有部分提取。" if truncated else ""
        prompt = self.CANON_IMPORTER_PROMPT.format(mode_label=self.MODE_LABELS[mode], truncation_note=truncation_note)
        response = await self.llm.generate_text(
            "fanfic_canon_import",
            prompt,
            {"source_name": source_name, "source_text": text, "mode": mode.value},
            model=self.config.model_for_task("architect"),
            temperature=0.3,
        )
        sections = self._parse_sections(response)
        full_document = self._build_full_document(source_name, mode, sections)
        canon = FanficCanon(
            book_id=book_id,
            source_name=source_name,
            mode=mode,
            world_rules=sections.get("world_rules", ""),
            character_profiles=sections.get("character_profiles", ""),
            key_events=sections.get("key_events", ""),
            power_system=sections.get("power_system", ""),
            writing_style=sections.get("writing_style", ""),
            full_document=full_document,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        self._save_canon(book_id, canon)
        return canon

    async def refresh_canon(self, book_id: str, source_text: str) -> FanficCanon:
        """Refresh existing canon while preserving source name and mode."""

        canon = self.get_canon(book_id)
        if canon is None:
            raise FileNotFoundError(f"fanfic canon not found: {book_id}")
        return await self.import_canon(book_id, source_text, canon.source_name, canon.mode)

    def get_canon(self, book_id: str) -> FanficCanon | None:
        """Load persisted fanfiction canon."""

        data = self.storage.read_json(self._json_path(book_id))
        if not data:
            return None
        return FanficCanon(**{**data, "mode": FanficMode(str(data.get("mode", "")))})

    def _parse_sections(self, response: str) -> dict[str, str]:
        pattern = r"=== SECTION: (\w+) ===\s*([\s\S]*?)(?==== SECTION:|$)"
        return {match.group(1): match.group(2).strip() for match in re.finditer(pattern, response)}

    def _build_full_document(self, source_name: str, mode: FanficMode, sections: dict[str, str]) -> str:
        meta = "\n".join(
            [
                "---",
                "meta:",
                f'  sourceFile: "{source_name}"',
                f'  fanficMode: "{mode.value}"',
                f'  generatedAt: "{datetime.now(timezone.utc).isoformat()}"',
            ]
        )
        return "\n".join(
            [
                f"# 同人正典（《{source_name}》）",
                "",
                "## 世界规则",
                sections.get("world_rules") or "（素材中未提取到明确世界规则）",
                "",
                "## 角色档案",
                sections.get("character_profiles") or "（素材中未提取到角色信息）",
                "",
                "## 关键事件时间线",
                sections.get("key_events") or "（素材中未提取到关键事件）",
                "",
                "## 力量体系",
                sections.get("power_system") or "（原作无明确力量体系）",
                "",
                "## 原作写作风格",
                sections.get("writing_style") or "（素材不足以提取风格特征）",
                "",
                meta,
            ]
        )

    def _save_canon(self, book_id: str, canon: FanficCanon) -> None:
        data = asdict(canon)
        data["mode"] = canon.mode.value
        self.storage.write_text(self._markdown_path(book_id), canon.full_document)
        self.storage.write_json(self._json_path(book_id), data)

    def _markdown_path(self, book_id: str) -> Path:
        return self.paths.book_dir(book_id) / "fanfic_canon.md"

    def _json_path(self, book_id: str) -> Path:
        return self.paths.book_dir(book_id) / "fanfic_canon.json"
