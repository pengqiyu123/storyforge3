import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { volumesApi } from "@/api/volumes";

export function useVolumes(bookId: string | undefined) {
  return useQuery({
    queryKey: ["volumes", bookId],
    queryFn: () => volumesApi.list(bookId ?? ""),
    enabled: Boolean(bookId)
  });
}

export function usePlanVolumes(bookId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { volumeCount: number; totalChapters: number }) =>
      volumesApi.plan(bookId, data.volumeCount, data.totalChapters),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["volumes", bookId] })
  });
}
