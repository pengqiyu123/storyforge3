import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { worldApi, type WorldConfig } from "@/api/world";

export function useWorld(bookId: string | undefined) {
  return useQuery({
    queryKey: ["world", bookId],
    queryFn: () => worldApi.get(bookId ?? ""),
    enabled: Boolean(bookId)
  });
}

export function useBuildWorld(bookId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { genre: string; seedBrief: string }) => worldApi.build(bookId, data.genre, data.seedBrief),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["world", bookId] })
  });
}

export function useUpdateWorld(bookId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (world: Omit<WorldConfig, "book_id">) => worldApi.update(bookId, world),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["world", bookId] })
  });
}
