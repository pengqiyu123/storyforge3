from __future__ import annotations

import json
from pathlib import Path

import pytest

from storyforge3.api.deps import get_provider_manager
from storyforge3.llm.provider_config import ProviderConfigManager


# ── fakes (mirror tests/test_provider_config.py but local for API isolation) ──

class FakeReader:
    """Stand-in for CCSwitchDBReader with a configurable db_available flag."""

    def __init__(self, providers: list[dict], *, db_available: bool = True) -> None:
        self.providers = providers
        self._db_available = db_available

    def read_all_providers(self, app_type: str | None = None) -> list[dict]:
        if app_type is None:
            return [dict(p) for p in self.providers]
        return [dict(p) for p in self.providers if p.get("cc_app_type") == app_type]

    def is_db_available(self) -> bool:
        return self._db_available


class FakeLLMService:
    def __init__(self, provider_config: dict, *, ok: bool = True, verified: dict | None = None) -> None:
        self.provider = {**provider_config, **(verified or {})}
        self.ok = ok

    async def check_health(self) -> bool:
        return self.ok


def _cc_provider(pid: str, *, api_key: str = "key", label: str | None = None) -> dict:
    return {
        "id": pid,
        "label": label or pid,
        "provider_key": pid,
        "base_url": f"https://{pid}.test/v1",
        "api_key": api_key,
        "has_api_key": bool(api_key),
        "model_id": "gpt-5.5",
        "enabled": False,
        "source": "cc-switch",
        "cc_app_type": "codex",
        "cc_api_format": "openai_responses",
        "cc_is_full_url": False,
        "cc_endpoint_auto_select": True,
        "cc_endpoint_candidates": [f"https://{pid}.test/v1"],
        "cc_base_url_raw": f"https://{pid}.test/v1",
        "cc_usage_base_url": None,
        "cc_is_current": False,
        "cc_category": "codex",
        "cc_last_verified_endpoint": None,
        "cc_last_verified_format": None,
        "cc_last_verified_model": None,
        "cc_probe_status": None,
        "cc_probe_message": None,
        "cc_health": None,
    }


def _write_providers(config, active_key, providers):
    """Write a providers.json directly into the test config dir."""
    config_dir = Path(config.providers_config_dir)
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "providers.json").write_text(
        json.dumps({"active_provider_key": active_key, "providers": providers}, ensure_ascii=False),
        encoding="utf-8",
    )


def _use_manager(client, manager: ProviderConfigManager) -> ProviderConfigManager:
    """Override get_provider_manager for one test (cleaned up by the autouse fixture)."""
    client.app.dependency_overrides[get_provider_manager] = lambda: manager
    return manager


@pytest.fixture(autouse=True)
def _reset_provider_manager_override(client):
    yield
    client.app.dependency_overrides.pop(get_provider_manager, None)


# ── existing ─────────────────────────────────────────────────────────────────

def test_list_providers_returns_imported_profiles(client, config):
    _write_providers(
        config,
        "codex",
        [
            {
                "id": "p1",
                "provider_key": "codex",
                "label": "Codex 直连中转",
                "base_url": "https://api.vip1129.cc/v1",
                "api_key": "secret-key-1234",
                "model_id": "gpt-5.5",
                "enabled": True,
            }
        ],
    )

    resp = client.get("/api/providers")
    assert resp.status_code == 200
    providers = resp.json()["data"]
    assert providers[0]["provider_key"] == "codex"
    assert providers[0]["api_key"] == "secr****1234"
    assert providers[0]["active"] is True


def test_provider_health_uses_llm_service(client, mock_llm):
    resp = client.get("/api/providers/health")
    assert resp.status_code == 200
    assert resp.json()["data"] == {"healthy": True}
    mock_llm.check_health.assert_awaited_once()


# ── available / import ───────────────────────────────────────────────────────

def test_list_available_returns_cc_providers_with_db_flag(client, config):
    manager = ProviderConfigManager(
        Path(config.providers_config_dir), reader=FakeReader([_cc_provider("cc-one", api_key="abcd1234efgh")])
    )
    _use_manager(client, manager)

    resp = client.get("/api/providers/available")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["db_available"] is True
    assert data["providers"][0]["provider_key"] == "cc-one"
    assert data["providers"][0]["has_api_key"] is True
    assert "****" in data["providers"][0]["api_key_preview"]


def test_list_available_when_db_missing_returns_empty(client, config):
    manager = ProviderConfigManager(Path(config.providers_config_dir), reader=FakeReader([], db_available=False))
    _use_manager(client, manager)

    resp = client.get("/api/providers/available")
    data = resp.json()["data"]
    assert data["db_available"] is False
    assert data["providers"] == []


def test_import_providers_endpoint_returns_imported_and_active(client, config):
    manager = ProviderConfigManager(
        Path(config.providers_config_dir), reader=FakeReader([_cc_provider("cc-one", api_key="secret-key-1234")])
    )
    _use_manager(client, manager)

    resp = client.post("/api/providers/import", json={"provider_ids": ["cc-one"]})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["imported"][0]["provider_key"] == "cc-one"
    assert data["imported"][0]["api_key"] == "secr****1234"
    assert data["active_provider_key"] == "cc-one"


# ── set active ───────────────────────────────────────────────────────────────

def test_set_active_endpoint_switches_active(client, config):
    _write_providers(
        config,
        "p1",
        [
            {"id": "p1", "provider_key": "p1", "label": "A", "base_url": "https://a.test", "api_key": "k1", "model_id": "m", "enabled": True},
            {"id": "p2", "provider_key": "p2", "label": "B", "base_url": "https://b.test", "api_key": "k2", "model_id": "m", "enabled": True},
        ],
    )

    resp = client.put("/api/providers/active", json={"provider_key": "p2"})
    assert resp.status_code == 200
    assert resp.json()["data"]["active_provider_key"] == "p2"

    active_flags = [p["active"] for p in client.get("/api/providers").json()["data"]]
    assert active_flags == [False, True]


def test_set_active_unknown_returns_error(client, config):
    _write_providers(config, None, [])

    resp = client.put("/api/providers/active", json={"provider_key": "nope"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "PROVIDER_NOT_IMPORTED"


# ── verify ───────────────────────────────────────────────────────────────────

def test_verify_provider_success_returns_resolved_fields(client, config):
    manager = ProviderConfigManager(
        Path(config.providers_config_dir),
        reader=FakeReader([_cc_provider("cc-one", api_key="key-one")]),
        service_factory=lambda pc: FakeLLMService(
            pc,
            ok=True,
            verified={
                "cc_last_verified_endpoint": "https://cc-one.test/v1/responses",
                "cc_last_verified_format": "openai_responses",
                "cc_last_verified_model": "gpt-5.5",
            },
        ),
    )
    _use_manager(client, manager)
    manager.import_providers(["cc-one"])

    resp = client.post("/api/providers/cc-one/verify")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "verified"
    assert data["resolved_model"] == "gpt-5.5"


def test_verify_provider_failure_returns_request_failed(client, config):
    manager = ProviderConfigManager(
        Path(config.providers_config_dir),
        reader=FakeReader([_cc_provider("cc-one", api_key="key-one")]),
        service_factory=lambda pc: FakeLLMService(pc, ok=False),
    )
    _use_manager(client, manager)
    manager.import_providers(["cc-one"])

    resp = client.post("/api/providers/cc-one/verify")
    data = resp.json()["data"]
    assert data["status"] == "request_failed"


def test_verify_provider_unknown_returns_not_found(client, config):
    _write_providers(config, None, [])
    resp = client.post("/api/providers/nope/verify")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


# ── remove ───────────────────────────────────────────────────────────────────

def test_remove_provider_recomputes_active(client, config):
    _write_providers(
        config,
        "p1",
        [
            {"id": "p1", "provider_key": "p1", "label": "A", "base_url": "https://a.test", "api_key": "k1", "model_id": "m", "enabled": True},
            {"id": "p2", "provider_key": "p2", "label": "B", "base_url": "https://b.test", "api_key": "k2", "model_id": "m", "enabled": True},
        ],
    )

    resp = client.delete("/api/providers/p1")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["removed_provider_key"] == "p1"
    assert data["active_provider_key"] == "p2"


def test_remove_provider_unknown_returns_not_found(client, config):
    _write_providers(config, None, [])
    resp = client.delete("/api/providers/nope")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


# ── routing (manual-mode reserved) ───────────────────────────────────────────

def test_get_routing_returns_model_overrides(client):
    resp = client.get("/api/providers/routing")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert set(data.keys()) == {
        "default_model",
        "writer_model",
        "auditor_model",
        "truth_extractor_model",
        "architect_model",
        "planner_model",
    }


def test_put_routing_stub_returns_not_implemented(client):
    resp = client.put(
        "/api/providers/routing",
        json={
            "default_model": "x",
            "writer_model": "",
            "auditor_model": "",
            "truth_extractor_model": "",
            "architect_model": "",
            "planner_model": "",
        },
    )
    assert resp.status_code == 501
    assert resp.json()["error"]["code"] == "NOT_IMPLEMENTED"
