import { useQuery } from "@tanstack/react-query";
import { truthApi } from "@/api/truth";

export function useTruthHistory(bookId: string) {
  return useQuery({
    queryKey: ["truth-history", bookId],
    queryFn: () => truthApi.history(bookId),
    enabled: Boolean(bookId),
    retry: false
  });
}

export function useTruthByChapter(bookId: string, chapterNo: number) {
  return useQuery({
    queryKey: ["truth-chapter", bookId, chapterNo],
    queryFn: () => truthApi.byChapter(bookId, chapterNo),
    enabled: Boolean(bookId && chapterNo),
    retry: false
  });
}
