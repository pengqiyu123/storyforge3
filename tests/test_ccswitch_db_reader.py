from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from storyforge3.llm.ccswitch_db_reader import CCSwitchDBReader


def create_ccswitch_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            CREATE TABLE providers (
                id TEXT,
                app_type TEXT,
                name TEXT,
                settings_config TEXT,
                category TEXT,
                meta TEXT,
                is_current INTEGER,
                sort_index INTEGER,
                created_at TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE provider_endpoints (
                id INTEGER,
                provider_id TEXT,
                app_type TEXT,
                url TEXT,
                added_at TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE provider_health (
                provider_id TEXT,
                app_type TEXT,
                is_healthy INTEGER,
                consecutive_failures INTEGER,
                last_error TEXT
            )
            """
        )
        connection.commit()
    finally:
        connection.close()


def insert_provider(
    path: Path,
    provider_id: str,
    app_type: str,
    settings: dict | str,
    *,
    name: str = "Provider",
    meta: dict | str | None = None,
) -> None:
    settings_value = settings if isinstance(settings, str) else json.dumps(settings)
    meta_value = meta if isinstance(meta, str) else json.dumps(meta or {})
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "INSERT INTO providers VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (provider_id, app_type, name, settings_value, "relay", meta_value, 0, 0, "2026-06-03"),
        )
        connection.commit()
    finally:
        connection.close()


def insert_endpoint(path: Path, provider_id: str, app_type: str, url: str) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "INSERT INTO provider_endpoints (provider_id, app_type, url, added_at) VALUES (?, ?, ?, ?)",
            (provider_id, app_type, url, "2026-06-03"),
        )
        connection.commit()
    finally:
        connection.close()


def insert_health(path: Path, provider_id: str, app_type: str, *, is_healthy: int, failures: int, error: str | None) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "INSERT INTO provider_health VALUES (?, ?, ?, ?, ?)",
            (provider_id, app_type, is_healthy, failures, error),
        )
        connection.commit()
    finally:
        connection.close()


def test_reader_parses_claude_provider_and_health(tmp_path: Path) -> None:
    database = tmp_path / "cc-switch.db"
    create_ccswitch_db(database)
    insert_provider(
        database,
        "claude-1",
        "claude",
        {
            "env": {
                "ANTHROPIC_BASE_URL": "https://claude-relay.test",
                "ANTHROPIC_AUTH_TOKEN": "claude-key",
                "ANTHROPIC_MODEL": "claude-sonnet-4",
            }
        },
        name="Claude Relay",
        meta={"apiFormat": "anthropic", "isFullUrl": False, "endpointAutoSelect": True},
    )
    insert_health(database, "claude-1", "claude", is_healthy=1, failures=0, error=None)

    providers = CCSwitchDBReader(database).read_all_providers("claude")

    assert providers == [
        {
            "id": "cc-claude-1",
            "label": "Claude Relay",
            "provider_key": "cc-claude-1",
            "base_url": "https://claude-relay.test",
            "api_key": "claude-key",
            "model_id": "claude-sonnet-4",
            "enabled": False,
            "source": "cc-switch",
            "cc_app_type": "claude",
            "cc_api_format": "anthropic",
            "cc_is_full_url": False,
            "cc_endpoint_auto_select": True,
            "cc_endpoint_candidates": ["https://claude-relay.test"],
            "cc_base_url_raw": "https://claude-relay.test",
            "cc_usage_base_url": None,
            "cc_last_verified_endpoint": None,
            "cc_last_verified_format": None,
            "cc_last_verified_model": None,
            "cc_probe_status": None,
            "cc_probe_message": None,
            "cc_health": {"is_healthy": True, "consecutive_failures": 0, "last_error": None},
        }
    ]


def test_reader_parses_codex_toml_and_endpoint_candidates_in_order(tmp_path: Path) -> None:
    database = tmp_path / "cc-switch.db"
    create_ccswitch_db(database)
    insert_provider(
        database,
        "codex-1",
        "codex",
        {
            "auth": {"OPENAI_API_KEY": "codex-key"},
            "config": (
                'model_provider = "relay"\n'
                'model = "gpt-5.5"\n'
                "[model_providers.relay]\n"
                'base_url = "https://codex-relay.test/v1"\n'
                'wire_api = "chat"\n'
            ),
        },
        meta={
            "apiFormat": None,
            "isFullUrl": True,
            "endpointAutoSelect": False,
            "usage_script": {"baseUrl": "https://usage-relay.test"},
        },
    )
    insert_endpoint(database, "codex-1", "codex", "https://candidate-a.test/v1")
    insert_endpoint(database, "codex-1", "codex", "https://codex-relay.test/v1")
    insert_endpoint(database, "codex-1", "codex", "https://candidate-a.test/v1")

    provider = CCSwitchDBReader(database).read_provider("cc-codex-1")

    assert provider is not None
    assert provider["api_key"] == "codex-key"
    assert provider["base_url"] == "https://codex-relay.test/v1"
    assert provider["model_id"] == "gpt-5.5"
    assert provider["cc_api_format"] == "openai_chat"
    assert provider["cc_is_full_url"] is True
    assert provider["cc_endpoint_auto_select"] is False
    assert provider["cc_endpoint_candidates"] == [
        "https://candidate-a.test/v1",
        "https://codex-relay.test/v1",
        "https://usage-relay.test",
    ]


def test_reader_preserves_blank_codex_model_for_relay_default(tmp_path: Path) -> None:
    database = tmp_path / "cc-switch.db"
    create_ccswitch_db(database)
    insert_provider(
        database,
        "codex-default",
        "codex",
        {
            "auth": {"OPENAI_API_KEY": "codex-key"},
            "config": (
                'model_provider = "relay"\n'
                "[model_providers.relay]\n"
                'base_url = "https://codex-relay.test/v1"\n'
                'wire_api = "responses"\n'
            ),
        },
    )

    provider = CCSwitchDBReader(database).read_provider("cc-codex-default")

    assert provider is not None
    assert provider["model_id"] == ""


def test_reader_parses_gemini_provider(tmp_path: Path) -> None:
    database = tmp_path / "cc-switch.db"
    create_ccswitch_db(database)
    insert_provider(
        database,
        "gemini-1",
        "gemini",
        {
            "env": {
                "GOOGLE_GEMINI_BASE_URL": "https://generativelanguage.googleapis.com",
                "GEMINI_API_KEY": "gemini-key",
                "GEMINI_MODEL": "gemini-2.5-pro",
            }
        },
    )

    provider = CCSwitchDBReader(database).read_provider("gemini-1")

    assert provider is not None
    assert provider["id"] == "cc-gemini-1"
    assert provider["cc_api_format"] == "gemini_native"
    assert provider["base_url"] == "https://generativelanguage.googleapis.com"
    assert provider["api_key"] == "gemini-key"
    assert provider["model_id"] == "gemini-2.5-pro"


def test_reader_empty_database_returns_empty_list(tmp_path: Path) -> None:
    database = tmp_path / "cc-switch.db"
    create_ccswitch_db(database)

    assert CCSwitchDBReader(database).read_all_providers() == []


def test_reader_damaged_json_does_not_crash(tmp_path: Path) -> None:
    database = tmp_path / "cc-switch.db"
    create_ccswitch_db(database)
    insert_provider(database, "broken-1", "claude", "{not json", meta="{also broken")

    providers = CCSwitchDBReader(database).read_all_providers()

    assert len(providers) == 1
    assert providers[0]["id"] == "cc-broken-1"
    assert providers[0]["base_url"] == ""
    assert providers[0]["api_key"] == ""
    assert providers[0]["cc_api_format"] == "anthropic"
    assert providers[0]["cc_endpoint_candidates"] == []


def test_reader_missing_database_returns_empty_list(tmp_path: Path) -> None:
    assert CCSwitchDBReader(tmp_path / "missing.db").read_all_providers() == []
