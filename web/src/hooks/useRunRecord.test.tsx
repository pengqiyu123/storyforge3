import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { runRecordKey, useCancelRun, useRunRecord } from "./useRunRecord";

describe("useRunRecord", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("fetches the persisted run record so refresh can recover state", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          ok: true,
          data: createRunRecord({ status: "running", current_stage: "draft" }),
          error: null
        })
      )
    );
    vi.stubGlobal("fetch", fetchMock);
    const queryClient = createQueryClient();
    const wrapper = createWrapper(queryClient);

    const { result } = renderHook(() => useRunRecord("biedale", 2), { wrapper });

    await waitFor(() => expect(result.current.data?.current_stage).toBe("draft"));
    expect(queryClient.getQueryData(runRecordKey("biedale", 2))).toEqual(result.current.data);
    expect(fetchMock).toHaveBeenCalledWith("/api/books/biedale/chapters/2/run", expect.any(Object));
  });

  it("treats a missing run record as idle", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          ok: false,
          data: null,
          error: { code: "CHAPTER_NOT_FOUND", message: "run not found" }
        })
      )
    );
    vi.stubGlobal("fetch", fetchMock);
    const queryClient = createQueryClient();
    const wrapper = createWrapper(queryClient);

    const { result } = renderHook(() => useRunRecord("biedale", 2), { wrapper });

    await waitFor(() => expect(result.current.data).toBeNull());
  });

  it("invalidates the run record and chapter status after cancel", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          ok: true,
          data: createRunRecord({ status: "cancelled" }),
          error: null
        })
      )
    );
    vi.stubGlobal("fetch", fetchMock);
    const queryClient = createQueryClient();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    const wrapper = createWrapper(queryClient);

    const { result } = renderHook(() => useCancelRun("biedale", 2), { wrapper });

    await act(async () => {
      await result.current.mutateAsync("run-1");
    });

    expect(fetchMock).toHaveBeenCalledWith("/api/books/biedale/chapters/2/run/run-1/cancel", expect.any(Object));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: runRecordKey("biedale", 2) });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["chapter-status", "biedale", 2] });
  });
});

function createQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

function createWrapper(queryClient: QueryClient) {
  return ({ children }: PropsWithChildren) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

function createRunRecord(overrides: Record<string, unknown> = {}) {
  return {
    run_id: "run-1",
    book_id: "biedale",
    chapter_no: 2,
    mode: "full",
    target_stages: ["plan", "draft", "audit", "revise", "approve", "truth", "export"],
    status: "pending",
    current_stage: null,
    started_at: "2026-06-15T01:00:00Z",
    updated_at: "2026-06-15T01:00:00Z",
    stage_results: {},
    llm_calls: [],
    error_code: null,
    error_message: null,
    resume_from: null,
    ...overrides
  };
}
