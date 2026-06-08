from __future__ import annotations

import pytest

from tests.conftest_api import write_imported_provider


@pytest.mark.asyncio
async def test_health_returns_ok(async_client):
    response = await async_client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["status"] == "ok"
    assert body["data"]["default_model"] == "test-model"


@pytest.mark.asyncio
async def test_list_providers(async_client, api_config):
    write_imported_provider(api_config)

    response = await async_client.get("/api/providers")

    assert response.status_code == 200
    providers = response.json()["data"]
    assert providers[0]["provider_key"] == "codex"
    assert providers[0]["api_key"] == "secr****1234"
