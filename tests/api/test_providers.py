from __future__ import annotations

import json
from pathlib import Path


def test_list_providers_returns_imported_profiles(client, config):
    config_dir = Path(config.providers_config_dir)
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "providers.json").write_text(
        json.dumps(
            {
                "active_provider_key": "codex",
                "providers": [
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
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
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
