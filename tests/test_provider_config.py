from __future__ import annotations

import json
from pathlib import Path

import pytest

from storyforge3.config import StoryForge3Config
from storyforge3.llm.factory import create_llm_service
from storyforge3.llm.provider_config import ProviderConfigManager, build_provider_from_profile, mask_api_key


def provider(provider_id: str, api_key: str, *, label: str | None = None) -> dict:
    return {
        "id": provider_id,
        "label": label or provider_id,
        "provider_key": provider_id,
        "base_url": f"https://{provider_id}.test/v1",
        "api_key": api_key,
        "model_id": "gpt-5.5",
        "enabled": False,
        "source": "cc-switch",
        "cc_app_type": "codex",
        "cc_api_format": "openai_responses",
        "cc_is_full_url": False,
        "cc_endpoint_auto_select": True,
        "cc_endpoint_candidates": [f"https://{provider_id}.test/v1"],
        "cc_base_url_raw": f"https://{provider_id}.test/v1",
        "cc_usage_base_url": None,
        "cc_last_verified_endpoint": None,
        "cc_last_verified_format": None,
        "cc_last_verified_model": None,
        "cc_probe_status": None,
        "cc_probe_message": None,
        "cc_health": None,
    }


class FakeReader:
    def __init__(self, providers: list[dict]) -> None:
        self.providers = providers

    def read_all_providers(self, app_type: str | None = None) -> list[dict]:
        if app_type is None:
            return [dict(item) for item in self.providers]
        return [dict(item) for item in self.providers if item.get("cc_app_type") == app_type]


class FakeLLMService:
    def __init__(self, provider_config: dict, *, ok: bool = True) -> None:
        self.provider = provider_config
        self.ok = ok

    async def check_health(self) -> bool:
        return self.ok


def test_empty_config_initializes_without_file(tmp_path: Path) -> None:
    manager = ProviderConfigManager(tmp_path, reader=FakeReader([]))

    assert manager.list_imported() == []
    assert manager.get_active() is None
    assert json.loads((tmp_path / "providers.json").read_text(encoding="utf-8")) == {
        "active_provider_key": None,
        "providers": [],
    }


def test_import_providers_merges_and_sets_first_keyed_provider_active(tmp_path: Path) -> None:
    manager = ProviderConfigManager(
        tmp_path,
        reader=FakeReader([provider("cc-empty", ""), provider("cc-keyed", "secret-key")]),
    )

    imported = manager.import_providers(["cc-empty", "cc-keyed"])

    assert [item["provider_key"] for item in imported] == ["cc-keyed"]
    assert manager.get_active()["provider_key"] == "cc-keyed"  # type: ignore[index]
    saved = json.loads((tmp_path / "providers.json").read_text(encoding="utf-8"))
    assert [item["provider_key"] for item in saved["providers"]] == ["cc-keyed"]
    assert saved["providers"][0]["enabled"] is True


def test_import_providers_rejects_no_key_selection_without_persisting(tmp_path: Path) -> None:
    manager = ProviderConfigManager(tmp_path, reader=FakeReader([provider("cc-empty", "")]))

    with pytest.raises(ValueError, match="No importable provider"):
        manager.import_providers(["cc-empty"])

    assert manager.list_imported(include_secrets=True) == []
    assert manager.get_active() is None


def test_list_available_masks_api_keys_without_persisting_masked_values(tmp_path: Path) -> None:
    manager = ProviderConfigManager(tmp_path, reader=FakeReader([provider("cc-one", "abcd1234efgh")]))

    available = manager.list_available()

    assert available[0]["api_key"] == "abcd****efgh"
    assert manager._reader.read_all_providers()[0]["api_key"] == "abcd1234efgh"  # noqa: SLF001


def test_import_preserves_existing_api_key_when_new_value_is_masked(tmp_path: Path) -> None:
    old = provider("cc-one", "real-secret")
    old["enabled"] = True
    (tmp_path / "providers.json").write_text(
        json.dumps({"active_provider_key": "cc-one", "providers": [old]}, ensure_ascii=False),
        encoding="utf-8",
    )
    incoming = provider("cc-one", "real****cret", label="Updated")
    manager = ProviderConfigManager(tmp_path, reader=FakeReader([incoming]))

    imported = manager.import_providers(["cc-one"])

    assert imported[0]["label"] == "Updated"
    assert imported[0]["api_key"] == "real****cret"
    assert imported[0]["enabled"] is True
    saved = manager.list_imported(include_secrets=True)
    assert saved[0]["api_key"] == "real-secret"


def test_set_active_and_build_runtime_provider(tmp_path: Path) -> None:
    first = provider("cc-one", "key-one")
    second = provider("cc-two", "key-two")
    manager = ProviderConfigManager(tmp_path, reader=FakeReader([first, second]))
    manager.import_providers(["cc-one", "cc-two"])

    manager.set_active("cc-two")

    active = manager.get_active()
    assert active is not None
    runtime = build_provider_from_profile(active)
    assert runtime["key"] == "cc-two"
    assert runtime["enabled"] is True
    assert runtime["cc_endpoint_candidates"] == ["https://cc-two.test/v1"]


def test_build_runtime_provider_preserves_blank_model_id() -> None:
    profile = provider("cc-relay", "key")
    profile.pop("model_id")

    runtime = build_provider_from_profile(profile)

    assert runtime["model_id"] == ""


def test_set_active_rejects_unknown_provider(tmp_path: Path) -> None:
    manager = ProviderConfigManager(tmp_path, reader=FakeReader([]))

    with pytest.raises(KeyError):
        manager.set_active("missing")


async def test_verify_provider_updates_verified_fields(tmp_path: Path) -> None:
    keyed = provider("cc-one", "key-one")
    manager = ProviderConfigManager(
        tmp_path,
        reader=FakeReader([keyed]),
        service_factory=lambda provider_config: FakeLLMService(
            {
                **provider_config,
                "cc_last_verified_endpoint": "https://cc-one.test/v1/responses",
                "cc_last_verified_format": "openai_responses",
                "cc_last_verified_model": "gpt-5.5",
            }
        ),
    )
    manager.import_providers(["cc-one"])

    result = await manager.verify_provider("cc-one")

    assert result["status"] == "verified"
    active = manager.get_active()
    assert active is not None
    assert active["cc_last_verified_endpoint"] == "https://cc-one.test/v1/responses"
    assert active["cc_last_verified_format"] == "openai_responses"
    assert active["cc_last_verified_model"] == "gpt-5.5"
    assert active["cc_probe_status"] == "verified"
    assert active["cc_probe_message"] == "已验证，可用于稿件生成"


async def test_verify_provider_records_failure(tmp_path: Path) -> None:
    manager = ProviderConfigManager(
        tmp_path,
        reader=FakeReader([provider("cc-one", "key-one")]),
        service_factory=lambda provider_config: FakeLLMService(provider_config, ok=False),
    )
    manager.import_providers(["cc-one"])

    result = await manager.verify_provider("cc-one")

    assert result["status"] == "request_failed"
    imported = manager.list_imported(include_secrets=True)
    assert imported[0]["cc_probe_status"] == "request_failed"


def test_remove_provider_recomputes_active_when_active_removed(tmp_path: Path) -> None:
    first = provider("cc-one", "key-one")
    second = provider("cc-two", "key-two")
    manager = ProviderConfigManager(tmp_path, reader=FakeReader([first, second]))
    manager.import_providers(["cc-one", "cc-two"])
    manager.set_active("cc-one")

    removed = manager.remove_provider("cc-one")

    assert removed is not None
    assert removed["provider_key"] == "cc-one"
    # api_key is masked on the returned profile
    assert "****" in removed["api_key"]
    active = manager.get_active()
    assert active is not None
    assert active["provider_key"] == "cc-two"


def test_remove_provider_leaves_active_when_other_removed(tmp_path: Path) -> None:
    first = provider("cc-one", "key-one")
    second = provider("cc-two", "key-two")
    manager = ProviderConfigManager(tmp_path, reader=FakeReader([first, second]))
    manager.import_providers(["cc-one", "cc-two"])
    manager.set_active("cc-one")

    removed = manager.remove_provider("cc-two")

    assert removed is not None
    assert removed["provider_key"] == "cc-two"
    active = manager.get_active()
    assert active is not None
    assert active["provider_key"] == "cc-one"


def test_remove_provider_unknown_returns_none(tmp_path: Path) -> None:
    manager = ProviderConfigManager(tmp_path, reader=FakeReader([]))
    assert manager.remove_provider("nope") is None


def test_is_db_available_delegates_to_reader(tmp_path: Path) -> None:
    class ReaderWithFlag:
        def __init__(self, flag: bool) -> None:
            self.flag = flag

        def read_all_providers(self, app_type: str | None = None) -> list[dict]:
            return []

        def is_db_available(self) -> bool:
            return self.flag

    assert ProviderConfigManager(tmp_path, reader=ReaderWithFlag(True)).is_db_available() is True
    assert ProviderConfigManager(tmp_path, reader=ReaderWithFlag(False)).is_db_available() is False


def test_mask_api_key() -> None:
    assert mask_api_key("") == ""
    assert mask_api_key("short") == "****"
    assert mask_api_key("abcd1234efgh") == "abcd****efgh"


def test_create_llm_service_loads_active_and_fallback_provider(tmp_path: Path) -> None:
    active = provider("cc-one", "key-one")
    active["enabled"] = True
    fallback = provider("cc-two", "key-two")
    fallback["enabled"] = True
    (tmp_path / "providers.json").write_text(
        json.dumps({"active_provider_key": "cc-one", "providers": [active, fallback]}, ensure_ascii=False),
        encoding="utf-8",
    )

    service = create_llm_service(
        StoryForge3Config(
            providers_config_dir=str(tmp_path),
            llm_timeout_seconds=111,
            llm_draft_timeout_seconds=333,
            llm_short_timeout_seconds=44,
        )
    )

    assert service.provider["key"] == "cc-one"
    assert service.fallback_provider is not None
    assert service.fallback_provider["key"] == "cc-two"
    assert service.default_timeout == 111
    assert service.draft_timeout == 333
    assert service.short_timeout == 44


def test_create_llm_service_without_active_provider_returns_unavailable_shell(tmp_path: Path) -> None:
    service = create_llm_service(StoryForge3Config(providers_config_dir=str(tmp_path)))

    assert service.provider == {}
    assert service.fallback_provider is None
