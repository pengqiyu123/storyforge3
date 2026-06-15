import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { reconcileKey, useInvalidateReconcile, useReconcile } from "./useReconcile";

describe("useReconcile", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("fetches book reconciliation", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          ok: true,
          data: {
            book_id: "biedale",
            chapters: [],
            inconsistent_count: 0,
            max_chapter: 0
          },
          error: null
        })
      )
    );
    vi.stubGlobal("fetch", fetchMock);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: PropsWithChildren) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;

    const { result } = renderHook(() => useReconcile("biedale"), { wrapper });

    await waitFor(() => expect(result.current.data?.book_id).toBe("biedale"));
    expect(fetchMock).toHaveBeenCalledWith("/api/books/biedale/reconcile", expect.any(Object));
    expect(queryClient.getQueryData(reconcileKey("biedale"))).toEqual(result.current.data);
  });

  it("invalidates reconciliation for chapter-changing mutations", async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    const wrapper = ({ children }: PropsWithChildren) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
    const { result } = renderHook(() => useInvalidateReconcile("biedale"), { wrapper });

    await act(async () => {
      await result.current();
    });

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: reconcileKey("biedale") });
  });
});
