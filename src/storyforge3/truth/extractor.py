from __future__ import annotations

from typing import Any

from storyforge3.models import TruthData
from storyforge3.prompts.registry import PromptRegistry


class TruthExtractionError(Exception):
    """Truth extraction failed and requires human review."""

    def __init__(self, chapter_no: int, reason: str):
        self.chapter_no = chapter_no
        self.reason = reason
        super().__init__(f"Chapter {chapter_no} truth extraction failed: {reason}")


class TruthExtractor:
    def __init__(self, client: Any, registry: PromptRegistry) -> None:
        self.client = client
        self.registry = registry

    async def extract(
        self,
        chapter_no: int,
        chapter_text: str,
        previous_truth: TruthData | None = None,
    ) -> TruthData:
        template = self.registry.get_latest("truth_extract")
        system_prompt = self.registry.render_system_prompt(template, chapter_no=chapter_no)
        payload = {
            "chapter_no": chapter_no,
            "chapter_text": chapter_text,
            "previous_truth": previous_truth.fact_assertions if previous_truth else (),
        }
        try:
            data = await self.client.generate_json(
                "truth_extract",
                system_prompt,
                payload,
                self._schema(),
                prompt_version=f"{template.prompt_id}:v{template.version}",
            )
        except Exception as exc:
            raise TruthExtractionError(chapter_no, str(exc)) from exc
        return self._parse(chapter_no, data)

    def _parse(self, chapter_no: int, data: dict) -> TruthData:
        facts = tuple(str(item) for item in data.get("fact_assertions", ()) if str(item).strip())
        if not facts:
            raise TruthExtractionError(chapter_no, "empty fact_assertions")
        return TruthData(
            chapter_no=chapter_no,
            source="runtime_native",
            fact_assertions=facts,
            character_updates=self._dict_items(data.get("character_updates", ())),
            relationship_updates=self._dict_items(data.get("relationship_updates", ())),
            hook_updates=self._dict_items(data.get("hook_updates", ())),
            irreversible_facts=tuple(str(item) for item in data.get("irreversible_facts", ())),
            notes=tuple(str(item) for item in data.get("notes", ())),
        )

    @staticmethod
    def _dict_items(values: object) -> tuple[dict, ...]:
        if not isinstance(values, (list, tuple)):
            return ()
        items: list[dict] = []
        for value in values:
            if isinstance(value, dict):
                if value:
                    items.append(dict(value))
                continue
            text = str(value).strip()
            if text:
                items.append({"summary": text})
        return tuple(items)

    @staticmethod
    def _schema() -> dict:
        return {
            "type": "object",
            "properties": {
                "fact_assertions": {"type": "array", "items": {"type": "string"}},
                "character_updates": {"type": "array"},
                "relationship_updates": {"type": "array"},
                "hook_updates": {"type": "array"},
                "irreversible_facts": {"type": "array", "items": {"type": "string"}},
                "notes": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["fact_assertions"],
        }
