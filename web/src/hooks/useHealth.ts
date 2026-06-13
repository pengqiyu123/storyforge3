import { useQuery } from "@tanstack/react-query";
import { healthApi } from "@/api/health";

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: healthApi.check
  });
}

// Canonical provider-list query lives in useProviders.ts (owns queryKey ["providers"]).
// Re-exported here for backward compatibility with existing `useProviders` imports.
export { useImportedProviders as useProviders } from "@/hooks/useProviders";
