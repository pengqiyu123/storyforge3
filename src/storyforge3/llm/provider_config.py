from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

from storyforge3.llm.ccswitch_db_reader import CCSwitchDBReader

DEFAULT_CCSWITCH_DB_PATH = Path.home() / ".cc-switch" / "cc-switch.db"
CONFIG_FILE_NAME = "providers.json"


class ProviderConfigManager:
    """Manage StoryForge3's imported provider profiles without writing CC-Switch data."""

    def __init__(
        self,
        config_dir: Path,
        *,
        ccswitch_db_path: Path | None = None,
        reader: Any | None = None,
        service_factory: Callable[[dict], Any] | None = None,
    ) -> None:
        self.config_dir = Path(config_dir)
        self.config_path = self.config_dir / CONFIG_FILE_NAME
        self._reader = reader or CCSwitchDBReader(ccswitch_db_path or DEFAULT_CCSWITCH_DB_PATH)
        self._service_factory = service_factory
        self._ensure_config()

    def list_available(self) -> list[dict]:
        return [self._mask_profile(provider) for provider in self._reader.read_all_providers()]

    def import_providers(self, provider_ids: list[str]) -> list[dict]:
        data = self._load()
        existing_by_id = {str(provider.get("id")): dict(provider) for provider in data["providers"]}
        selected_ids = set(provider_ids)
        imported: list[dict] = []
        for provider in self._reader.read_all_providers():
            if provider.get("id") not in selected_ids and provider.get("provider_key") not in selected_ids:
                continue
            profile = dict(provider)
            old = existing_by_id.get(str(profile.get("id")))
            if old is not None:
                profile = self._merge_profile(old, profile)
            profile["enabled"] = bool(profile.get("api_key"))
            existing_by_id[str(profile["id"])] = profile
            imported.append(profile)
        data["providers"] = self._merged_provider_list(data["providers"], existing_by_id, imported)
        if not self._active_has_key(data):
            data["active_provider_key"] = self._first_keyed_provider_key(data["providers"])
        self._save(data)
        return [self._mask_profile(item) for item in imported]

    def get_active(self) -> dict | None:
        data = self._load()
        active_key = data.get("active_provider_key")
        if not active_key:
            return None
        for profile in data["providers"]:
            if profile.get("provider_key") == active_key:
                return dict(profile)
        return None

    def get_active_provider(self) -> dict | None:
        active = self.get_active()
        return build_provider_from_profile(active) if active is not None else None

    def set_active(self, provider_key: str) -> None:
        data = self._load()
        if not any(profile.get("provider_key") == provider_key for profile in data["providers"]):
            raise KeyError(f"provider not imported: {provider_key}")
        data["active_provider_key"] = provider_key
        self._save(data)

    def list_imported(self, *, include_secrets: bool = False) -> list[dict]:
        providers = [dict(provider) for provider in self._load()["providers"]]
        if include_secrets:
            return providers
        return [self._mask_profile(provider) for provider in providers]

    def verify_provider(self, provider_key: str) -> dict:
        data = self._load()
        profile = self._find_profile(data, provider_key)
        provider = build_provider_from_profile(profile)
        try:
            service = self._build_service(provider)
            ok = asyncio.run(service.check_health())
        except Exception as exc:
            self._write_probe_failure(data, profile, str(exc))
            return {"status": "request_failed", "message": str(exc)}
        if not ok:
            self._write_probe_failure(data, profile, "provider health check failed")
            return {"status": "request_failed", "message": "provider health check failed"}
        self._write_probe_success(data, profile, service)
        return {
            "status": "verified",
            "resolved_endpoint": profile.get("cc_last_verified_endpoint"),
            "resolved_format": profile.get("cc_last_verified_format"),
            "resolved_model": profile.get("cc_last_verified_model"),
        }

    def _build_service(self, provider: dict) -> Any:
        if self._service_factory is not None:
            return self._service_factory(provider)
        from storyforge3.llm.llm_service import LLMService

        return LLMService(provider)

    def _ensure_config(self) -> None:
        if self.config_path.exists():
            return
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self._save({"active_provider_key": None, "providers": []})

    def _load(self) -> dict:
        self._ensure_config()
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        providers = data.get("providers")
        return {
            "active_provider_key": data.get("active_provider_key"),
            "providers": providers if isinstance(providers, list) else [],
        }

    def _save(self, data: dict) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _merge_profile(old: dict, new: dict) -> dict:
        merged = {**old, **new}
        if is_masked_api_key(str(new.get("api_key") or "")):
            merged["api_key"] = old.get("api_key", "")
        return merged

    @staticmethod
    def _merged_provider_list(original: list[dict], by_id: dict[str, dict], imported: list[dict]) -> list[dict]:
        result: list[dict] = []
        emitted: set[str] = set()
        for provider in original:
            provider_id = str(provider.get("id"))
            if provider_id in by_id:
                result.append(by_id[provider_id])
                emitted.add(provider_id)
        for provider in imported:
            provider_id = str(provider.get("id"))
            if provider_id not in emitted:
                result.append(provider)
                emitted.add(provider_id)
        return result

    @staticmethod
    def _active_has_key(data: dict) -> bool:
        active_key = data.get("active_provider_key")
        return any(
            profile.get("provider_key") == active_key and profile.get("api_key")
            for profile in data.get("providers", [])
        )

    @staticmethod
    def _first_keyed_provider_key(providers: list[dict]) -> str | None:
        for profile in providers:
            if profile.get("api_key"):
                return str(profile.get("provider_key"))
        return None

    @staticmethod
    def _find_profile(data: dict, provider_key: str) -> dict:
        for profile in data["providers"]:
            if profile.get("provider_key") == provider_key:
                return profile
        raise KeyError(f"provider not imported: {provider_key}")

    def _write_probe_success(self, data: dict, profile: dict, service: Any) -> None:
        service_provider = getattr(service, "provider", None)
        if isinstance(service_provider, dict):
            profile["cc_last_verified_endpoint"] = service_provider.get("cc_last_verified_endpoint")
            profile["cc_last_verified_format"] = service_provider.get("cc_last_verified_format")
            profile["cc_last_verified_model"] = service_provider.get("cc_last_verified_model")
        profile["cc_probe_status"] = "verified"
        profile["cc_probe_message"] = "已验证，可用于稿件生成"
        self._save(data)

    def _write_probe_failure(self, data: dict, profile: dict, message: str) -> None:
        profile["cc_probe_status"] = "request_failed"
        profile["cc_probe_message"] = message
        self._save(data)

    @staticmethod
    def _mask_profile(profile: dict) -> dict:
        masked = deepcopy(profile)
        masked["api_key"] = mask_api_key(str(masked.get("api_key") or ""))
        return masked


def build_provider_from_profile(profile: dict) -> dict:
    return {
        "key": str(profile.get("provider_key") or "").strip(),
        "label": str(profile.get("label") or "").strip(),
        "base_url": str(profile.get("base_url") or "").strip(),
        "api_key": str(profile.get("api_key") or "").strip(),
        "model_id": str(profile.get("model_id") or "").strip(),
        "enabled": bool(profile.get("enabled") and profile.get("api_key")),
        "source": profile.get("source"),
        "cc_app_type": profile.get("cc_app_type"),
        "cc_api_format": profile.get("cc_api_format"),
        "cc_is_full_url": profile.get("cc_is_full_url"),
        "cc_endpoint_auto_select": profile.get("cc_endpoint_auto_select"),
        "cc_endpoint_candidates": list(profile.get("cc_endpoint_candidates", [])),
        "cc_base_url_raw": profile.get("cc_base_url_raw"),
        "cc_usage_base_url": profile.get("cc_usage_base_url"),
        "cc_last_verified_endpoint": profile.get("cc_last_verified_endpoint"),
        "cc_last_verified_format": profile.get("cc_last_verified_format"),
        "cc_last_verified_model": profile.get("cc_last_verified_model"),
    }


def mask_api_key(api_key: str) -> str:
    if not api_key:
        return ""
    if len(api_key) < 8:
        return "****"
    return f"{api_key[:4]}****{api_key[-4:]}"


def is_masked_api_key(api_key: str) -> bool:
    return "****" in api_key
