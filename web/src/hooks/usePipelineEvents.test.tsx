import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { usePipelineEvents } from "./usePipelineEvents";

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
});
