from __future__ import annotations

import json
import sqlite3
import tomllib
from dataclasses import dataclass
from pathlib import Path

from storyforge3.config import StoryForge3Config


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    base_url: str
    api_key: str
    default_model: str


class CCSwitchConfigReader:
    """Deprecated settings.json reader retained for compatibility.

    New code uses CCSwitchDBReader plus project-local providers.json instead.
    """

    def __init__(self, config: StoryForge3Config) -> None:
        self.config = config
        self.last_error: str | None = None

    def read_current_provider(self) -> ProviderConfig | None:
        self.last_error = None
        provider_id = self._read_provider_id()
        if not provider_id:
            return None
        return self._read_provider_config(provider_id)

    def _read_provider_id(self) -> str | None:
        app_type = getattr(self.config, "ccswitch_app_type", "codex")
        settings_path = getattr(self.config, "ccswitch_settings_path", "C:/Users/pengq/.cc-switch/settings.json")
        path = Path(settings_path)
        if not path.exists():
            self.last_error = f"CCSwitch settings not found: {path}"
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            self.last_error = f"Failed to read CCSwitch settings: {exc}"
            return None
        key = f"currentProvider{app_type.capitalize()}"
        provider_id = data.get(key)
        if not isinstance(provider_id, str) or not provider_id:
            self.last_error = f"Missing active provider id in settings key: {key}"
            return None
        return provider_id

    def _read_provider_config(self, provider_id: str) -> ProviderConfig | None:
        app_type = getattr(self.config, "ccswitch_app_type", "codex")
        db_path = getattr(self.config, "ccswitch_db_path", "C:/Users/pengq/.cc-switch/cc-switch.db")
        path = Path(db_path)
        if not path.exists():
            self.last_error = f"CCSwitch database not found: {path}"
            return None
        try:
            row = self._query_provider(path, provider_id, app_type)
        except sqlite3.Error as exc:
            self.last_error = f"Failed to query CCSwitch database: {exc}"
            return None
        if row is None:
            self.last_error = f"Provider not found for app_type={app_type}: {provider_id}"
            return None
        return self._parse_provider_row(row)

    def _query_provider(self, path: Path, provider_id: str, app_type: str) -> tuple[str, str] | None:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            cursor = connection.execute(
                "SELECT name, settings_config FROM providers WHERE id = ? AND app_type = ?",
                (provider_id, app_type),
            )
            row = cursor.fetchone()
            return (str(row[0]), str(row[1])) if row else None
        finally:
            connection.close()

    def _parse_provider_row(self, row: tuple[str, str]) -> ProviderConfig | None:
        name, settings_json = row
        try:
            settings = json.loads(settings_json)
        except json.JSONDecodeError as exc:
            self.last_error = f"Invalid provider settings JSON: {exc}"
            return None
        settings = self._normalize_settings(settings)
        base_url = str(settings.get("base_url") or settings.get("baseURL") or "").rstrip("/")
        api_key = str(settings.get("api_key") or settings.get("apiKey") or "")
        model = str(settings.get("model") or settings.get("default_model") or settings.get("defaultModel") or "")
        if not base_url or not api_key or not model:
            self.last_error = "Provider settings missing base_url, api_key, or model"
            return None
        return ProviderConfig(name, self._normalize_base_url(base_url), api_key, model)

    def _normalize_settings(self, settings: dict) -> dict:
        if "config" not in settings:
            return settings
        config_text = settings.get("config")
        if not isinstance(config_text, str):
            return settings
        try:
            parsed = tomllib.loads(config_text)
        except tomllib.TOMLDecodeError as exc:
            self.last_error = f"Invalid CCSwitch config TOML: {exc}"
            return settings
        provider_name = str(parsed.get("model_provider") or "")
        provider_table = parsed.get("model_providers", {}).get(provider_name, {}) if provider_name else {}
        auth = settings.get("auth", {}) if isinstance(settings.get("auth"), dict) else {}
        return {
            "base_url": provider_table.get("base_url"),
            "api_key": auth.get("OPENAI_API_KEY") or provider_table.get("experimental_bearer_token"),
            "model": parsed.get("model"),
        }

    @staticmethod
    def _normalize_base_url(base_url: str) -> str:
        return base_url if base_url.endswith("/v1") else f"{base_url}/v1"
