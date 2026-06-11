import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { chapterStatusKey, useChapterUpdateText } from "./useChapters";

describe("useChapterUpdateText", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("saves text and invalidates chapter status", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          ok: true,
          data: {
            book_id: "lurenjia",
            chapter_no: 2,
            status: "needs_review",
            title: "第2章",
            text: "林默保存了人工修改。",
            content_hash: "newhash1",
            actual_chars: 9,
            error: null
          },
          error: null
        })
      )
    );
    vi.stubGlobal("fetch", fetchMock);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    const wrapper = ({ children }: PropsWithChildren) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
    const { result } = renderHook(() => useChapterUpdateText("lurenjia"), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({
        chapterNo: 2,
        text: "林默保存了人工修改。",
        expectedHash: "oldhash1"
      });
    });

    await waitFor(() => expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: chapterStatusKey("lurenjia", 2) }));
  });
});
