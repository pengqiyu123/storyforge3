import { api } from "./client";

export interface HealthStatus {
  status: string;
  default_model: string;
  books_dir: string;
}

export interface Provider {
  id: string;
  provider_key: string;
  label: string;
  base_url: string;
  model_id: string;
  enabled: boolean;
  active?: boolean;
  source?: string | null;
  cc_probe_status?: string | null;
  cc_last_verified_model?: string | null;
}

export const healthApi = {
  check: () => api.get<HealthStatus>("/api/health"),
  providers: () => api.get<Provider[]>("/api/providers")
};
