import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { shortStoriesApi, type CreateShortRequest } from "@/api/shorts";

export function shortsKey() {
  return ["shorts"] as const;
}

export function shortKey(bookId: string | undefined) {
  return ["short", bookId] as const;
}

export function useShorts() {
  return useQuery({
    queryKey: shortsKey(),
    queryFn: shortStoriesApi.list
  });
}

export function useShort(bookId: string | undefined) {
  return useQuery({
    queryKey: shortKey(bookId),
    queryFn: () => shortStoriesApi.get(bookId ?? ""),
    enabled: Boolean(bookId),
    retry: false
  });
}

export function useCreateShort() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateShortRequest) => shortStoriesApi.create(data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: shortsKey() })
  });
}

function useShortMutation<TArgs extends unknown[], TResult>(bookId: string, fn: (bookId: string, ...args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (args: TArgs = [] as unknown as TArgs) => fn(bookId, ...args),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: shortKey(bookId) });
      queryClient.invalidateQueries({ queryKey: shortsKey() });
    }
  });
}

export function useShortPlan(bookId: string) {
  return useShortMutation(bookId, shortStoriesApi.plan);
}

export function useShortDraft(bookId: string) {
  return useShortMutation(bookId, shortStoriesApi.draft);
}

export function useShortAudit(bookId: string) {
  return useShortMutation(bookId, shortStoriesApi.audit);
}

export function useShortRevise(bookId: string) {
  return useShortMutation(bookId, shortStoriesApi.revise);
}

export function useShortExport(bookId: string) {
  return useShortMutation(bookId, shortStoriesApi.export);
}

export function useShortRunFull(bookId: string) {
  return useShortMutation(bookId, shortStoriesApi.runFullPipeline);
}
