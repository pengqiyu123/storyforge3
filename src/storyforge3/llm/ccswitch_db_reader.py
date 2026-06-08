from __future__ import annotations

import json
import sqlite3
import tomllib
from pathlib import Path
from typing import Any

VALID_API_FORMATS = {"openai_chat", "openai_responses", "anthropic", "gemini_native"}


class CCSwitchDBReader:
    """Read provider profiles from the CC-Switch SQLite database without writing to it."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)

    def read_all_providers(self, app_type: str | None = None) -> list[dict]:
        if not self.db_path.exists():
            return []
        try:
            with self._connect() as connection:
                rows = self._query_provider_rows(connection, app_type)
                return [self._provider_from_row(connection, row) for row in rows]
        except sqlite3.Error:
            return []

    def read_provider(self, provider_id: str) -> dict | None:
        provider_id = self._strip_cc_prefix(provider_id)
        if not self.db_path.exists():
            return None
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    """
                    SELECT id, app_type, name, settings_config, category, meta, is_current, sort_index, created_at
                    FROM providers
                    WHERE id = ?
                    ORDER BY sort_index ASC, created_at ASC
                    LIMIT 1
                    """,
                    (provider_id,),
                )
                row = cursor.fetchone()
                return self._provider_from_row(connection, row) if row else None
        except sqlite3.Error:
            return None

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(f"file:{self.db_path}?mode=ro&nolock=1", uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _query_provider_rows(connection: sqlite3.Connection, app_type: str | None) -> list[sqlite3.Row]:
        if app_type is None:
            cursor = connection.execute(
                """
                SELECT id, app_type, name, settings_config, category, meta, is_current, sort_index, created_at
                FROM providers
                ORDER BY sort_index ASC, created_at ASC
                """
            )
        else:
            cursor = connection.execute(
                """
                SELECT id, app_type, name, settings_config, category, meta, is_current, sort_index, created_at
                FROM providers
                WHERE app_type = ?
                ORDER BY sort_index ASC, created_at ASC
                """,
                (app_type,),
            )
        return list(cursor.fetchall())

    def _provider_from_row(self, connection: sqlite3.Connection, row: sqlite3.Row) -> dict:
        provider_id = str(row["id"] or "")
        app_type = str(row["app_type"] or "")
        settings = self._safe_json(row["settings_config"])
        meta = self._safe_json(row["meta"])
        extracted = self._extract_settings(app_type, settings)
        cc_api_format = self._meta_api_format(meta) or extracted["api_format"]
        usage_base_url = self._usage_base_url(meta)
        endpoint_candidates = self._endpoint_candidates(
            connection,
            provider_id,
            app_type,
            extracted["base_url"],
            usage_base_url,
        )
        return {
            "id": f"cc-{provider_id}",
            "label": str(row["name"] or ""),
            "provider_key": f"cc-{provider_id}",
            "base_url": extracted["base_url"],
            "api_key": extracted["api_key"],
            "model_id": extracted["model_id"],
            "enabled": False,
            "source": "cc-switch",
            "cc_app_type": app_type,
            "cc_api_format": cc_api_format,
            "cc_is_full_url": self._optional_bool(meta.get("isFullUrl")),
            "cc_endpoint_auto_select": self._optional_bool(meta.get("endpointAutoSelect")),
            "cc_endpoint_candidates": endpoint_candidates,
            "cc_base_url_raw": extracted["base_url"],
            "cc_usage_base_url": usage_base_url,
            "cc_last_verified_endpoint": None,
            "cc_last_verified_format": None,
            "cc_last_verified_model": None,
            "cc_probe_status": None,
            "cc_probe_message": None,
            "cc_health": self._health(connection, provider_id, app_type),
        }

    def _extract_settings(self, app_type: str, settings: dict[str, Any]) -> dict[str, str]:
        if app_type == "claude":
            env = self._dict(settings.get("env"))
            return {
                "base_url": self._string(env.get("ANTHROPIC_BASE_URL")),
                "api_key": self._string(env.get("ANTHROPIC_AUTH_TOKEN") or env.get("ANTHROPIC_API_KEY")),
                "model_id": self._string(env.get("ANTHROPIC_MODEL")),
                "api_format": "anthropic",
            }
        if app_type == "gemini":
            env = self._dict(settings.get("env"))
            return {
                "base_url": self._string(env.get("GOOGLE_GEMINI_BASE_URL")),
                "api_key": self._string(env.get("GEMINI_API_KEY")),
                "model_id": self._string(env.get("GEMINI_MODEL")),
                "api_format": "gemini_native",
            }
        if app_type == "codex":
            return self._extract_codex_settings(settings)
        return {"base_url": "", "api_key": "", "model_id": "", "api_format": "openai_responses"}

    def _extract_codex_settings(self, settings: dict[str, Any]) -> dict[str, str]:
        auth = self._dict(settings.get("auth"))
        parsed = self._safe_toml(settings.get("config"))
        provider_table = self._codex_model_provider(parsed)
        wire_api = self._string(provider_table.get("wire_api") or parsed.get("wire_api"))
        api_format = {"chat": "openai_chat", "responses": "openai_responses"}.get(wire_api, "openai_responses")
        return {
            "base_url": self._string(provider_table.get("base_url") or parsed.get("base_url")),
            "api_key": self._string(auth.get("OPENAI_API_KEY") or provider_table.get("experimental_bearer_token")),
            "model_id": self._string(parsed.get("model") or provider_table.get("model")),
            "api_format": api_format,
        }

    def _codex_model_provider(self, parsed: dict[str, Any]) -> dict[str, Any]:
        model_providers = self._dict(parsed.get("model_providers"))
        provider_name = self._string(parsed.get("model_provider"))
        if provider_name and isinstance(model_providers.get(provider_name), dict):
            return dict(model_providers[provider_name])
        for value in model_providers.values():
            if isinstance(value, dict):
                return dict(value)
        return {}

    def _endpoint_candidates(
        self,
        connection: sqlite3.Connection,
        provider_id: str,
        app_type: str,
        base_url: str,
        usage_base_url: str | None,
    ) -> list[str]:
        values: list[str] = []
        try:
            cursor = connection.execute(
                """
                SELECT url
                FROM provider_endpoints
                WHERE provider_id = ? AND app_type = ?
                ORDER BY id ASC, added_at ASC
                """,
                (provider_id, app_type),
            )
            values.extend(self._string(row["url"]) for row in cursor.fetchall())
        except sqlite3.Error:
            values = []
        values.extend([base_url, usage_base_url or ""])
        return self._dedupe(value for value in values if value)

    @staticmethod
    def _health(connection: sqlite3.Connection, provider_id: str, app_type: str) -> dict | None:
        try:
            cursor = connection.execute(
                """
                SELECT is_healthy, consecutive_failures, last_error
                FROM provider_health
                WHERE provider_id = ? AND app_type = ?
                LIMIT 1
                """,
                (provider_id, app_type),
            )
            row = cursor.fetchone()
        except sqlite3.Error:
            return None
        if row is None:
            return None
        return {
            "is_healthy": bool(row["is_healthy"]),
            "consecutive_failures": int(row["consecutive_failures"] or 0),
            "last_error": row["last_error"],
        }

    @staticmethod
    def _safe_json(value: object) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if not isinstance(value, str) or not value.strip():
            return {}
        try:
            data = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _safe_toml(value: object) -> dict[str, Any]:
        if not isinstance(value, str) or not value.strip():
            return {}
        try:
            data = tomllib.loads(value)
        except tomllib.TOMLDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _usage_base_url(meta: dict[str, Any]) -> str | None:
        usage_script = meta.get("usage_script")
        if not isinstance(usage_script, dict):
            return None
        value = CCSwitchDBReader._string(usage_script.get("baseUrl"))
        return value or None

    @staticmethod
    def _meta_api_format(meta: dict[str, Any]) -> str | None:
        value = CCSwitchDBReader._string(meta.get("apiFormat"))
        return value if value in VALID_API_FORMATS else None

    @staticmethod
    def _optional_bool(value: object) -> bool | None:
        return value if isinstance(value, bool) else None

    @staticmethod
    def _dict(value: object) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _string(value: object) -> str:
        return value.strip() if isinstance(value, str) else ""

    @staticmethod
    def _strip_cc_prefix(provider_id: str) -> str:
        return provider_id[3:] if provider_id.startswith("cc-") else provider_id

    @staticmethod
    def _dedupe(values: object) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for value in values:
            text = str(value).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            deduped.append(text)
        return deduped
