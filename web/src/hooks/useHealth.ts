import { useQuery } from "@tanstack/react-query";
import { healthApi } from "@/api/health";

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: healthApi.check
  });
}

export function useProviders() {
  return useQuery({
    queryKey: ["providers"],
    queryFn: healthApi.providers
  });
}
