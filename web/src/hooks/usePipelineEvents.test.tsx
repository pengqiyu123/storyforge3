import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { usePipelineEvents } from "./usePipelineEvents";

const toastMocks = vi.hoisted(() => ({
  error: vi.fn(),
  info: vi.fn(),
  success: vi.fn()
}));

vi.mock("sonner", () => ({
  toast: {
    error: toastMocks.error,
    info: toastMocks.info,
    success: toastMocks.success
  }
}));

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onerror: (() => void) | null = null;
  url: string;
  closed = false;

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  close() {
    this.closed = true;
  }
}

describe("usePipelineEvents", () => {
  afterEach(() => {
    FakeEventSource.instances = [];
    Reflect.deleteProperty(window, "__TAURI_INTERNALS__");
    vi.restoreAllMocks();
    toastMocks.error.mockReset();
    toastMocks.info.mockReset();
    toastMocks.success.mockReset();
  });

  it("opens filtered event stream and forwards parsed events", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const onEvent = vi.fn();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: PropsWithChildren) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;

    const { unmount } = renderHook(() => usePipelineEvents("lurenjia", 2, onEvent), { wrapper });

    expect(FakeEventSource.instances[0].url).toBe("/api/events?book_id=lurenjia&chapter_no=2");

    act(() => {
      FakeEventSource.instances[0].onmessage?.(
        new MessageEvent("message", {
          data: JSON.stringify({ type: "pipeline:complete", book_id: "lurenjia", chapter_no: 2, stage: "draft", message: "完成" })
        })
      );
    });

    expect(onEvent).toHaveBeenCalledWith(expect.objectContaining({ stage: "draft" }));
    expect(toastMocks.success).toHaveBeenCalledWith("完成");
    unmount();
    expect(FakeEventSource.instances[0].closed).toBe(true);
  });

  it("opens desktop event streams against the local Python API in Tauri mode", () => {
    Object.defineProperty(window, "__TAURI_INTERNALS__", { configurable: true, value: {} });
    vi.stubGlobal("EventSource", FakeEventSource);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: PropsWithChildren) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;

    const { unmount } = renderHook(() => usePipelineEvents("lurenjia", 3), { wrapper });

    expect(FakeEventSource.instances[0].url).toBe("http://127.0.0.1:8000/api/events?book_id=lurenjia&chapter_no=3");
    unmount();
  });

  it("forwards llm progress events without showing toast", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const onEvent = vi.fn();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: PropsWithChildren) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;

    renderHook(() => usePipelineEvents("lurenjia", 4, onEvent), { wrapper });

    act(() => {
      FakeEventSource.instances[0].onmessage?.(
        createMockSSEEvent("llm:progress", {
          stage: "draft",
          detail: { completed: 2, total: 5 }
        })
      );
    });

    expect(onEvent).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "llm:progress",
        detail: { completed: 2, total: 5 }
      })
    );
    expect(toastMocks.info).not.toHaveBeenCalled();
    expect(toastMocks.success).not.toHaveBeenCalled();
    expect(toastMocks.error).not.toHaveBeenCalled();
  });

  it("forwards llm chunk events without showing toast", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const onEvent = vi.fn();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: PropsWithChildren) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;

    renderHook(() => usePipelineEvents("lurenjia", 5, onEvent), { wrapper });

    act(() => {
      FakeEventSource.instances[0].onmessage?.(
        createMockSSEEvent("llm:chunk", {
          stage: "draft",
          detail: { text: "林默" }
        })
      );
    });

    expect(onEvent).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "llm:chunk",
        detail: { text: "林默" }
      })
    );
    expect(toastMocks.info).not.toHaveBeenCalled();
    expect(toastMocks.success).not.toHaveBeenCalled();
    expect(toastMocks.error).not.toHaveBeenCalled();
  });

  it("does not show toast for pipeline progress style events", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const onEvent = vi.fn();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: PropsWithChildren) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;

    renderHook(() => usePipelineEvents("lurenjia", 6, onEvent), { wrapper });

    act(() => {
      FakeEventSource.instances[0].onmessage?.(
        createMockSSEEvent("pipeline:progress", {
          stage: "draft",
          message: "处理中"
        })
      );
    });

    expect(onEvent).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "pipeline:progress",
        message: "处理中"
      })
    );
    expect(toastMocks.info).not.toHaveBeenCalled();
    expect(toastMocks.success).not.toHaveBeenCalled();
    expect(toastMocks.error).not.toHaveBeenCalled();
  });

  it("reconnects with exponential backoff on stream error", () => {
    vi.useFakeTimers();
    vi.stubGlobal("EventSource", FakeEventSource);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: PropsWithChildren) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;

    const { unmount } = renderHook(() => usePipelineEvents("lurenjia", 7), { wrapper });

    expect(FakeEventSource.instances).toHaveLength(1);

    act(() => {
      FakeEventSource.instances[0].onerror?.();
    });
    expect(FakeEventSource.instances[0].closed).toBe(true);

    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(FakeEventSource.instances).toHaveLength(2);

    act(() => {
      FakeEventSource.instances[1].onerror?.();
    });
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(FakeEventSource.instances).toHaveLength(3);

    act(() => {
      FakeEventSource.instances[2].onmessage?.(
        new MessageEvent("message", {
          data: JSON.stringify({ type: "pipeline:complete", book_id: "lurenjia", chapter_no: 7, stage: "draft", message: "ok" })
        })
      );
    });

    act(() => {
      FakeEventSource.instances[2].onerror?.();
    });
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(FakeEventSource.instances).toHaveLength(4);

    unmount();
    vi.useRealTimers();
  });

  it("stops reconnecting after the max retry count", () => {
    vi.useFakeTimers();
    vi.stubGlobal("EventSource", FakeEventSource);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: PropsWithChildren) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;

    const { unmount } = renderHook(() => usePipelineEvents("lurenjia", 8), { wrapper });

    const delays = [1000, 2000, 4000, 8000, 16000];
    for (const delay of delays) {
      const current = FakeEventSource.instances[FakeEventSource.instances.length - 1];
      act(() => {
        current.onerror?.();
      });
      act(() => {
        vi.advanceTimersByTime(delay);
      });
    }
    expect(FakeEventSource.instances).toHaveLength(6);

    act(() => {
      FakeEventSource.instances[5].onerror?.();
    });
    act(() => {
      vi.advanceTimersByTime(60000);
    });
    expect(FakeEventSource.instances).toHaveLength(6);

    unmount();
    vi.useRealTimers();
  });
});

function createMockSSEEvent(
  type: string,
  overrides?: Record<string, unknown>
): MessageEvent<string> {
  return new MessageEvent("message", {
    data: JSON.stringify({
      type,
      book_id: "test-book",
      chapter_no: 1,
      ...overrides
    })
  });
}
