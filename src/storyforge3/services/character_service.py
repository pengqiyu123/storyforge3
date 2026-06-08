from __future__ import annotations

from dataclasses import asdict
from typing import Any

from storyforge3.config import StoryForge3Config
from storyforge3.models import Character, CharacterRole, Relationship
from storyforge3.services.json_text import parse_json_text
from storyforge3.storage import BookStorage, StoragePaths


CHARACTER_SYSTEM_PROMPT = "你是中文网文角色设计师。请只输出 JSON。"
CHARACTER_TEXT_PROMPT = """你是中文网文角色设计师。
请用 ```json ... ``` 输出一个 JSON object，字段必须符合请求。
单角色必须包含 name, role, profile, personality。
批量角色必须包含 characters，可选 relationships。
不要输出解释。"""


class CharacterService:
    def __init__(self, llm: Any, storage: BookStorage, paths: StoragePaths, config: StoryForge3Config) -> None:
        self.llm = llm
        self.storage = storage
        self.paths = paths
        self.config = config

    async def create(self, book_id: str, spec: str) -> Character:
        payload = {"book_id": book_id, "spec": spec}
        data = await self._generate_character_payload("character_create", "character_create_text", payload, self._schema())
        character = self._load_character(book_id, data)
        characters = [item for item in await self.list_characters(book_id) if item.name != character.name]
        characters.append(character)
        self._save_characters(book_id, characters)
        return character

    async def create_batch(self, book_id: str, specs: tuple[str, ...]) -> tuple[Character, ...]:
        payload = {"book_id": book_id, "specs": specs}
        data = await self._generate_character_payload("character_create_batch", "character_create_batch_text", payload, self._batch_schema())
        characters = tuple(self._load_character(book_id, item) for item in data.get("characters", ()))
        relationships = tuple(self._load_relationship(item) for item in data.get("relationships", ()))
        self._save_characters(book_id, list(characters))
        self._save_relationships(book_id, list(relationships))
        return characters

    async def list_characters(self, book_id: str) -> list[Character]:
        data = self.storage.read_json(self.paths.characters(book_id)) or {"characters": []}
        return [self._load_character(book_id, item) for item in data.get("characters", [])]

    async def get_relationships(self, book_id: str) -> list[Relationship]:
        data = self.storage.read_json(self.paths.relationships(book_id)) or {"relationships": []}
        return [self._load_relationship(item) for item in data.get("relationships", [])]

    async def update(self, book_id: str, name: str, updates: dict) -> Character:
        characters = await self.list_characters(book_id)
        for index, character in enumerate(characters):
            if character.name == name:
                updated = Character(**{**asdict(character), **updates})
                characters[index] = updated
                self._save_characters(book_id, characters)
                return updated
        raise FileNotFoundError(f"character not found: {name}")

    def _save_characters(self, book_id: str, characters: list[Character]) -> None:
        data = [self._dump_character(item) for item in characters]
        self.storage.write_json(self.paths.characters(book_id), {"characters": data})

    def _save_relationships(self, book_id: str, relationships: list[Relationship]) -> None:
        self.storage.write_json(self.paths.relationships(book_id), {"relationships": [asdict(item) for item in relationships]})

    @staticmethod
    def _load_character(book_id: str, data: dict) -> Character:
        return Character(book_id, str(data["name"]), CharacterService._normalize_role(data.get("role")), str(data["profile"]), str(data["personality"]), tuple(data.get("abilities", ())), str(data.get("arc_direction", "")))

    @staticmethod
    def _dump_character(character: Character) -> dict:
        data = asdict(character)
        data["role"] = character.role.value
        return data

    @staticmethod
    def _load_relationship(data: dict) -> Relationship:
        return Relationship(str(data["character_a"]), str(data["character_b"]), str(data["relation_type"]), str(data["description"]))

    @staticmethod
    def _schema() -> dict:
        return {"type": "object", "required": ["name", "role", "profile", "personality"]}

    @staticmethod
    def _batch_schema() -> dict:
        return {"type": "object", "required": ["characters"]}

    @staticmethod
    def _normalize_role(value: object) -> CharacterRole:
        raw = str(value or "").strip().lower()
        if raw in {role.value for role in CharacterRole}:
            return CharacterRole(raw)
        if "主角" in raw or "protagonist" in raw:
            return CharacterRole.PROTAGONIST
        if any(marker in raw for marker in ("主要", "配角", "major", "mentor", "ally", "反派", "对手")):
            return CharacterRole.MAJOR
        return CharacterRole.MINOR

    async def _generate_character_payload(self, json_task: str, text_task: str, payload: dict, schema: dict) -> dict:
        model = self.config.model_for_task("architect")
        try:
            return await self.llm.generate_json(
                json_task,
                CHARACTER_SYSTEM_PROMPT,
                payload,
                schema,
                model=model,
            )
        except Exception:
            text = await self.llm.generate_text(
                text_task,
                CHARACTER_TEXT_PROMPT,
                {**payload, "response_schema": schema},
                model=model,
                temperature=0.4,
            )
            return parse_json_text(text)
