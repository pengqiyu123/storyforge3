import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { runsApi, type RunRecord } from "@/api/runs";
import { chapterStatusKey } from "@/hooks/useChapters";

export function runRecordKey(bookId: string, chapterNo: number) {
  return ["run-record", bookId, chapterNo] as const;
}

export function useRunRecord(bookId: string | undefined, chapterNo: number | undefined) {
  return useQuery({
    queryKey: runRecordKey(bookId ?? "", chapterNo ?? 0),
    queryFn: async (): Promise<RunRecord | null> => {
      try {
        return await runsApi.get(bookId ?? "", chapterNo ?? 0);
      } catch (error) {
        const message = error instanceof Error ? error.message : "";
        if (message.includes("未找到") || message.includes("不存在") || message.toLowerCase().includes("not found")) {
          return null;
        }
        throw error;
      }
    },
    enabled: Boolean(bookId && chapterNo),
    retry: false
  });
}

export function useCancelRun(bookId: string, chapterNo: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => runsApi.cancel(bookId, chapterNo, runId),
    onSuccess: (record) => {
      queryClient.setQueryData(runRecordKey(bookId, chapterNo), record);
      queryClient.invalidateQueries({ queryKey: runRecordKey(bookId, chapterNo) });
      queryClient.invalidateQueries({ queryKey: chapterStatusKey(bookId, chapterNo) });
    }
  });
}
