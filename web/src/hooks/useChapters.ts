import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { chaptersApi } from "@/api/chapters";

export function chapterStatusKey(bookId: string, chapterNo: number) {
  return ["chapter-status", bookId, chapterNo] as const;
}

export function useChapterStatus(bookId: string, chapterNo: number) {
  return useQuery({
    queryKey: chapterStatusKey(bookId, chapterNo),
    queryFn: () => chaptersApi.getStatus(bookId, chapterNo),
    enabled: Boolean(bookId && chapterNo),
    retry: false
  });
}

function useChapterMutation<TArgs extends unknown[], TResult>(
  bookId: string,
  fn: (bookId: string, chapterNo: number, ...args: TArgs) => Promise<TResult>
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ chapterNo, args = [] as unknown as TArgs }: { chapterNo: number; args?: TArgs }) => fn(bookId, chapterNo, ...args),
    onSuccess: (_result, variables) => queryClient.invalidateQueries({ queryKey: chapterStatusKey(bookId, variables.chapterNo) })
  });
}

export function useChapterPlan(bookId: string) {
  return useChapterMutation(bookId, chaptersApi.plan);
}

export function useChapterDraft(bookId: string) {
  return useChapterMutation(bookId, chaptersApi.draft);
}

export function useChapterAudit(bookId: string) {
  return useChapterMutation(bookId, chaptersApi.audit);
}

export function useChapterRevise(bookId: string) {
  return useChapterMutation(bookId, chaptersApi.revise);
}

export function useChapterUpdateText(bookId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ chapterNo, text, expectedHash }: { chapterNo: number; text: string; expectedHash?: string }) =>
      chaptersApi.updateText(bookId, chapterNo, {
        text,
        expected_hash: expectedHash
      }),
    onSuccess: (_result, variables) => queryClient.invalidateQueries({ queryKey: chapterStatusKey(bookId, variables.chapterNo) })
  });
}

export function useChapterApprove(bookId: string) {
  return useChapterMutation(bookId, chaptersApi.approve);
}

export function useChapterExport(bookId: string) {
  return useChapterMutation(bookId, chaptersApi.exportChapter);
}

export function useRunFullPipeline(bookId: string) {
  return useChapterMutation(bookId, chaptersApi.runFullPipeline);
}
