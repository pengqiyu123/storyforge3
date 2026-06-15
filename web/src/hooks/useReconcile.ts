import { useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { reconcileApi } from "@/api/reconcile";

export function reconcileKey(bookId: string) {
  return ["reconcile", bookId] as const;
}

export function useReconcile(bookId: string | undefined) {
  return useQuery({
    queryKey: reconcileKey(bookId ?? ""),
    queryFn: () => reconcileApi.get(bookId ?? ""),
    enabled: Boolean(bookId),
    retry: false
  });
}

export function useInvalidateReconcile(bookId: string) {
  const queryClient = useQueryClient();
  return useCallback(() => queryClient.invalidateQueries({ queryKey: reconcileKey(bookId) }), [bookId, queryClient]);
}
