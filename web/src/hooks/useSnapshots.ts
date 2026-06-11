import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { snapshotsApi } from "@/api/snapshots";

// Adapted from CC-Switch useBackupManager.ts: keep the list + restore query/mutation shape.
export function useSnapshotList(bookId: string) {
  return useQuery({
    queryKey: ["snapshots", bookId],
    queryFn: () => snapshotsApi.list(bookId),
    enabled: Boolean(bookId),
    retry: false
  });
}

export function useSnapshotRestore(bookId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (snapshotPath: string) => snapshotsApi.restore(bookId, snapshotPath),
    onSuccess: () => {
      // Adapted from useBackupManager's invalidateQueries pattern after a destructive restore action.
      queryClient.invalidateQueries({ queryKey: ["chapter-status"] });
      queryClient.invalidateQueries({ queryKey: ["truth-history"] });
      queryClient.invalidateQueries({ queryKey: ["snapshots", bookId] });
    }
  });
}
