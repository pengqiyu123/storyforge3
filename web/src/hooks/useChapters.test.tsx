import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { chapterPlanKey, chapterStatusKey, useChapterPlanState, useChapterStatus, useChapterUpdateText } from "./useChapters";

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

  it("maps missing chapter status to empty fallback state", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          ok: false,
          data: null,
          error: { code: "CHAPTER_NOT_FOUND", message: "章节不存在" }
        }),
        { status: 404 }
      )
    );
    vi.stubGlobal("fetch", fetchMock);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: PropsWithChildren) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
    const { result } = renderHook(() => useChapterStatus("lurenjia", 5), { wrapper });

    await waitFor(() => expect(result.current.data?.status).toBe("empty"));
    expect(result.current.data).toEqual({
      book_id: "lurenjia",
      chapter_no: 5,
      status: "empty",
      title: "未命名",
      text: ""
    });
  });

  it("loads persisted chapter plan state", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          ok: true,
          data: {
            chapter_no: 2,
            goal: "进入副楼",
            outline_node: "夜灯仓纠纷升级",
            arc_context: "沈听澜开始主动接话",
            must_keep: ["保留巡夜队压力"],
            must_avoid: ["直接解释世界观"],
            style_emphasis: ["短句推进"]
          },
          error: null
        })
      )
    );
    vi.stubGlobal("fetch", fetchMock);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: PropsWithChildren) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
    const { result } = renderHook(() => useChapterPlanState("lurenjia", 2), { wrapper });

    await waitFor(() => expect(result.current.data?.goal).toBe("进入副楼"));
    expect(queryClient.getQueryData(chapterPlanKey("lurenjia", 2))).toEqual(result.current.data);
  });
});
