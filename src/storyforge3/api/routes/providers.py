"""REST routes for the CCSwitch provider-switching panel.

Exposes the import/switch/verify/remove operations the Web UI needs on top of
``ProviderConfigManager``, plus a reserved manual-mode routing pair (GET works;
PUT is a 501 stub until config persistence lands). All outputs mask ``api_key``
(e.g. ``abcd****1234``); secrets never leave the process in plaintext.

The manager is injected via ``get_provider_manager`` so API tests can override it
with a FakeReader / FakeLLMService-backed manager instead of touching the real
CC-Switch DB or placing real LLM calls.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from storyforge3.api.deps import get_config, get_llm_service, get_provider_manager
from storyforge3.api.errors import ApiError, not_found
from storyforge3.api.response import ok
from storyforge3.config import StoryForge3Config
from storyforge3.llm.provider_config import ProviderConfigManager

router = APIRouter(prefix="/providers", tags=["providers"])


# ── Pydantic models ──────────────────────────────────────────────────────────
# Every *Out model carries `api_key`/`api_key_preview` as the MASKED string.

class CcHealthOut(BaseModel):
    is_healthy: bool | None = None
    consecutive_failures: int | None = None
    last_error: str | None = None


class ImportedProviderOut(BaseModel):
    id: str
    provider_key: str
    label: str
    base_url: str
    model_id: str
    enabled: bool
    active: bool = False
    source: str | None = None
    api_key: str  # masked
    cc_app_type: str | None = None
    cc_api_format: str | None = None
    cc_is_full_url: bool | None = None
    cc_endpoint_auto_select: bool | None = None
    cc_endpoint_candidates: list[str] = []
    cc_last_verified_endpoint: str | None = None
    cc_last_verified_format: str | None = None
    cc_last_verified_model: str | None = None
    cc_probe_status: str | None = None
    cc_probe_message: str | None = None
    cc_health: CcHealthOut | None = None


class CCSwitchProviderInfoOut(BaseModel):
    id: str
    label: str
    provider_key: str
    base_url: str
    has_api_key: bool
    api_key_preview: str  # masked
    model_id: str
    cc_app_type: str | None = None
    cc_category: str | None = None
    cc_is_current: bool = False
    cc_api_format: str | None = None
    cc_is_full_url: bool | None = None
    cc_endpoint_auto_select: bool | None = None
    cc_endpoint_candidates: list[str] = []
    cc_health: CcHealthOut | None = None


class AvailableProvidersResponse(BaseModel):
    providers: list[CCSwitchProviderInfoOut]
    db_available: bool


class ImportProvidersRequest(BaseModel):
    provider_ids: list[str]


class ImportProvidersResponse(BaseModel):
    imported: list[ImportedProviderOut]
    active_provider_key: str | None = None


class SetActiveProviderRequest(BaseModel):
    provider_key: str


class SetActiveProviderResponse(BaseModel):
    active_provider_key: str


class VerifyProviderResponse(BaseModel):
    status: str
    resolved_endpoint: str | None = None
    resolved_format: str | None = None
    resolved_model: str | None = None
    message: str | None = None


class RemoveProviderResponse(BaseModel):
    removed_provider_key: str | None = None
    active_provider_key: str | None = None


class ProviderRouting(BaseModel):
    """Per-task model overrides — the manual-mode surface (layer-2 routing)."""
    default_model: str
    writer_model: str
    auditor_model: str
    truth_extractor_model: str
    architect_model: str
    planner_model: str


# ── helpers ──────────────────────────────────────────────────────────────────

def _health_out(raw: object) -> CcHealthOut | None:
    return CcHealthOut(**raw) if isinstance(raw, dict) else None


def _to_imported_out(profile: dict, active_key: str | None) -> ImportedProviderOut:
    return ImportedProviderOut(
        id=str(profile.get("id") or ""),
        provider_key=str(profile.get("provider_key") or ""),
        label=str(profile.get("label") or ""),
        base_url=str(profile.get("base_url") or ""),
        model_id=str(profile.get("model_id") or ""),
        enabled=bool(profile.get("enabled")),
        active=(profile.get("provider_key") == active_key),
        source=profile.get("source"),
        api_key=str(profile.get("api_key") or ""),  # already masked by list_imported
        cc_app_type=profile.get("cc_app_type"),
        cc_api_format=profile.get("cc_api_format"),
        cc_is_full_url=profile.get("cc_is_full_url"),
        cc_endpoint_auto_select=profile.get("cc_endpoint_auto_select"),
        cc_endpoint_candidates=list(profile.get("cc_endpoint_candidates") or []),
        cc_last_verified_endpoint=profile.get("cc_last_verified_endpoint"),
        cc_last_verified_format=profile.get("cc_last_verified_format"),
        cc_last_verified_model=profile.get("cc_last_verified_model"),
        cc_probe_status=profile.get("cc_probe_status"),
        cc_probe_message=profile.get("cc_probe_message"),
        cc_health=_health_out(profile.get("cc_health")),
    )


def _to_available_out(profile: dict) -> CCSwitchProviderInfoOut:
    return CCSwitchProviderInfoOut(
        id=str(profile.get("id") or ""),
        label=str(profile.get("label") or ""),
        provider_key=str(profile.get("provider_key") or ""),
        base_url=str(profile.get("base_url") or ""),
        has_api_key=bool(profile.get("has_api_key")),
        api_key_preview=str(profile.get("api_key") or ""),  # masked by list_available
        model_id=str(profile.get("model_id") or ""),
        cc_app_type=profile.get("cc_app_type"),
        cc_category=profile.get("cc_category"),
        cc_is_current=bool(profile.get("cc_is_current")),
        cc_api_format=profile.get("cc_api_format"),
        cc_is_full_url=profile.get("cc_is_full_url"),
        cc_endpoint_auto_select=profile.get("cc_endpoint_auto_select"),
        cc_endpoint_candidates=list(profile.get("cc_endpoint_candidates") or []),
        cc_health=_health_out(profile.get("cc_health")),
    )


def _active_key(manager: ProviderConfigManager) -> str | None:
    active = manager.get_active()
    return active.get("provider_key") if active else None


# ── routes ───────────────────────────────────────────────────────────────────

@router.get("")
async def list_providers(manager: ProviderConfigManager = Depends(get_provider_manager)):
    """List imported providers (masked). The active row carries ``active=true``."""
    active_key = _active_key(manager)
    providers = [_to_imported_out(p, active_key) for p in manager.list_imported()]
    return ok(providers)


@router.get("/available")
async def list_available_providers(manager: ProviderConfigManager = Depends(get_provider_manager)):
    """List providers available to import from the CC-Switch SQLite DB."""
    providers = [_to_available_out(p) for p in manager.list_available()]
    return ok(AvailableProvidersResponse(providers=providers, db_available=manager.is_db_available()))


@router.post("/import")
async def import_providers(
    request: ImportProvidersRequest,
    manager: ProviderConfigManager = Depends(get_provider_manager),
):
    """Import selected CC-Switch providers into the project-local config."""
    try:
        imported = manager.import_providers(request.provider_ids)
    except ValueError as exc:
        raise ApiError(
            status=400,
            code="NO_IMPORTABLE_PROVIDER",
            message=str(exc),
        ) from exc
    active_key = _active_key(manager)
    return ok(
        ImportProvidersResponse(
            imported=[_to_imported_out(p, active_key) for p in imported],
            active_provider_key=active_key,
        )
    )


@router.put("/active")
async def set_active_provider(
    request: SetActiveProviderRequest,
    manager: ProviderConfigManager = Depends(get_provider_manager),
):
    """Switch the active provider. Raises PROVIDER_NOT_IMPORTED when unknown."""
    try:
        manager.set_active(request.provider_key)
    except KeyError as exc:
        raise ApiError(
            status=400,
            code="PROVIDER_NOT_IMPORTED",
            message=f"Provider not imported: {request.provider_key}",
        ) from exc
    return ok(SetActiveProviderResponse(active_provider_key=request.provider_key))


@router.post("/{provider_key}/verify")
async def verify_provider(
    provider_key: str,
    manager: ProviderConfigManager = Depends(get_provider_manager),
):
    """Health-probe one provider. Returns status=verified|request_failed."""
    if not any(p.get("provider_key") == provider_key for p in manager.list_imported()):
        raise not_found(f"Provider not imported: {provider_key}")
    result = await manager.verify_provider(provider_key)
    return ok(VerifyProviderResponse(**result))


@router.delete("/{provider_key}")
async def remove_provider(
    provider_key: str,
    manager: ProviderConfigManager = Depends(get_provider_manager),
):
    """Remove an imported provider; recomputes active if it was active."""
    removed = manager.remove_provider(provider_key)
    if removed is None:
        raise not_found(f"Provider not imported: {provider_key}")
    return ok(
        RemoveProviderResponse(
            removed_provider_key=provider_key,
            active_provider_key=_active_key(manager),
        )
    )


@router.get("/routing")
async def get_provider_routing(config: StoryForge3Config = Depends(get_config)):
    """Return the current per-task model routing (manual-mode surface)."""
    return ok(
        ProviderRouting(
            default_model=config.default_model,
            writer_model=config.writer_model,
            auditor_model=config.auditor_model,
            truth_extractor_model=config.truth_extractor_model,
            architect_model=config.architect_model,
            planner_model=config.planner_model,
        )
    )


@router.put("/routing")
async def update_provider_routing(routing: ProviderRouting):
    """Stub: per-task routing persistence is not implemented yet (manual mode).

    StoryForge3Config is env/.env-backed with no write path; a config_override.json
    loader is the prerequisite. Returns 501 rather than silently mutating memory.
    The body is still validated against ProviderRouting so the contract is fixed.
    """
    raise ApiError(
        status=501,
        code="NOT_IMPLEMENTED",
        message="手动模式模型路由持久化尚未实现（待 config_override 落地）。",
    )


@router.get("/health")
async def provider_health(llm=Depends(get_llm_service)):
    """Probe the currently active provider's connectivity."""
    healthy = await llm.check_health()
    return ok({"healthy": healthy})
