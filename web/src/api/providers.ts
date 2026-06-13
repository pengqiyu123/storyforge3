/**
 * CCSwitch provider API client.
 *
 * Types mirror the Pydantic models in `src/storyforge3/api/routes/providers.py`.
 * All `api_key` / `api_key_preview` fields are masked by the backend (e.g. `abcd****1234`);
 * plaintext secrets are never sent to the client.
 */
import { api } from "./client";

/** Health info mirrored from the CC-Switch DB (may be null). */
export interface CcHealth {
  is_healthy?: boolean | null;
  consecutive_failures?: number | null;
  last_error?: string | null;
}

/** A provider imported into the project-local config (GET /api/providers row). */
export interface ImportedProvider {
  id: string;
  provider_key: string;
  label: string;
  base_url: string;
  model_id: string;
  enabled: boolean;
  active?: boolean;
  source?: string | null;
  api_key?: string; // masked
  cc_app_type?: string | null;
  cc_api_format?: string | null;
  cc_is_full_url?: boolean | null;
  cc_endpoint_auto_select?: boolean | null;
  cc_endpoint_candidates?: string[];
  cc_last_verified_endpoint?: string | null;
  cc_last_verified_format?: string | null;
  cc_last_verified_model?: string | null;
  cc_probe_status?: "verified" | "request_failed" | null;
  cc_probe_message?: string | null;
  cc_health?: CcHealth | null;
}

/** A provider available to import from the CC-Switch DB (import dialog row). */
export interface CCSwitchProviderInfo {
  id: string;
  label: string;
  provider_key: string;
  base_url: string;
  has_api_key: boolean;
  api_key_preview?: string; // masked
  model_id: string;
  cc_app_type?: string | null;
  cc_category?: string | null;
  cc_is_current?: boolean;
  cc_api_format?: string | null;
  cc_is_full_url?: boolean | null;
  cc_endpoint_auto_select?: boolean | null;
  cc_endpoint_candidates?: string[];
  cc_health?: CcHealth | null;
}

export interface AvailableProvidersResponse {
  providers: CCSwitchProviderInfo[];
  db_available: boolean;
}

export interface ImportProvidersResponse {
  imported: ImportedProvider[];
  active_provider_key: string | null;
}

export interface VerifyResult {
  status: "verified" | "request_failed";
  resolved_endpoint?: string | null;
  resolved_format?: string | null;
  resolved_model?: string | null;
  message?: string | null;
}

export interface RemoveProviderResponse {
  removed_provider_key: string | null;
  active_provider_key: string | null;
}

/** Per-task model overrides — the reserved manual-mode (layer-2) routing surface. */
export interface ProviderRouting {
  default_model: string;
  writer_model: string;
  auditor_model: string;
  truth_extractor_model: string;
  architect_model: string;
  planner_model: string;
}

export const providersApi = {
  listImported: () => api.get<ImportedProvider[]>("/api/providers"),
  listAvailable: () => api.get<AvailableProvidersResponse>("/api/providers/available"),
  import: (providerIds: string[]) =>
    api.post<ImportProvidersResponse>("/api/providers/import", { provider_ids: providerIds }),
  setActive: (providerKey: string) =>
    api.put<{ active_provider_key: string }>("/api/providers/active", { provider_key: providerKey }),
  verify: (providerKey: string) =>
    api.post<VerifyResult>(`/api/providers/${encodeURIComponent(providerKey)}/verify`, {}),
  remove: (providerKey: string) =>
    api.delete<RemoveProviderResponse>(`/api/providers/${encodeURIComponent(providerKey)}`),
  getRouting: () => api.get<ProviderRouting>("/api/providers/routing"),
  updateRouting: (routing: ProviderRouting) => api.put<ProviderRouting>("/api/providers/routing", routing)
};
