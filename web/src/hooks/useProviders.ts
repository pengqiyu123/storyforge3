/**
 * TanStack Query hooks for the CCSwitch provider panel.
 *
 * Query-key ownership: `["providers"]` is the canonical key for the imported list.
 * Every switching/import/verify/remove mutation invalidates it so the panel and
 * every active-badge consumer stay in sync. `["providers","available"]` is scoped
 * to the import dialog (fetched on open). `["providers","routing"]` is reserved
 * for manual mode.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { providersApi, type ProviderRouting } from "@/api/providers";

export function useImportedProviders() {
  return useQuery({
    queryKey: ["providers"],
    queryFn: providersApi.listImported,
    retry: false
  });
}

export function useAvailableProviders(enabled: boolean) {
  return useQuery({
    queryKey: ["providers", "available"],
    queryFn: providersApi.listAvailable,
    enabled,
    retry: false,
    staleTime: 0
  });
}

export function useSwitchProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (providerKey: string) => providersApi.setActive(providerKey),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["providers"] })
  });
}

export function useImportProviders() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (providerIds: string[]) => providersApi.import(providerIds),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["providers"] })
  });
}

export function useVerifyProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (providerKey: string) => providersApi.verify(providerKey),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["providers"] })
  });
}

export function useRemoveProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (providerKey: string) => providersApi.remove(providerKey),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["providers"] })
  });
}

// ── Reserved manual-mode (layer-2 routing) ─────────────────────────────────
// GET works today; PUT currently hits the backend 501 stub until config
// persistence lands. Defined now so the future RoutingPanel needs no backend churn.
export function useProviderRouting() {
  return useQuery({
    queryKey: ["providers", "routing"],
    queryFn: providersApi.getRouting,
    retry: false
  });
}

export function useUpdateRouting() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (routing: ProviderRouting) => providersApi.updateRouting(routing),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["providers", "routing"] })
  });
}
