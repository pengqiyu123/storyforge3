import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { RunRecord } from "@/api/runs";
import { runRecordKey } from "./useRunRecord";
import { useRunEvents } from "./useRunEvents";

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

describe("useRunEvents", () => {
  afterEach(() => {
    FakeEventSource.instances = [];
    Reflect.deleteProperty(window, "__TAURI_INTERNALS__");
    vi.restoreAllMocks();
  });

  it("opens a filtered stream without rebuilding when the event callback changes", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const queryClient = createQueryClient();
    const first = vi.fn();
    const second = vi.fn();
    const wrapper = createWrapper(queryClient);

    const { rerender, unmount } = renderHook(({ onEvent }) => useRunEvents("biedale", 2, onEvent), {
      wrapper,
      initialProps: { onEvent: first }
    });
    rerender({ onEvent: second });

    expect(FakeEventSource.instances).toHaveLength(1);
    act(() => {
      FakeEventSource.instances[0].onmessage?.(sse("stage:start", { run_id: "run-1", stage: "draft" }));
    });

    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledWith(expect.objectContaining({ type: "stage:start", stage: "draft" }));
    unmount();
    expect(FakeEventSource.instances[0].closed).toBe(true);
  });

  it("updates the cached run record for run and stage events", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const queryClient = createQueryClient();
    queryClient.setQueryData(runRecordKey("biedale", 2), createRunRecord({ status: "pending" }));
    const wrapper = createWrapper(queryClient);

    renderHook(() => useRunEvents("biedale", 2), { wrapper });

    act(() => {
      emit("run:start", { run_id: "run-1", detail: { mode: "full", target_stages: ["plan", "draft"] } });
      emit("stage:start", { run_id: "run-1", stage: "draft", message: "开始 draft" });
      emit("stage:progress", { run_id: "run-1", stage: "draft", detail: { completed: 1, total: 3 } });
      emit("llm:chunk", { run_id: "run-1", stage: "draft", detail: { text: "第一段。" } });
      emit("stage:complete", { run_id: "run-1", stage: "draft", detail: { chars: 4 } });
      emit("run:complete", { run_id: "run-1", detail: { final_status: "completed" } });
    });

    const cached = queryClient.getQueryData<RunRecord>(runRecordKey("biedale", 2));
    expect(cached).toMatchObject({
      run_id: "run-1",
      status: "completed",
      current_stage: null,
      stage_results: {
        draft: expect.objectContaining({ status: "completed", summary: { chars: 4 } })
      }
    });
    expect(cached?.live).toMatchObject({
      stage: "draft",
      progress: { completed: 1, total: 3 },
      streamText: "第一段。"
    });
  });

  it("records waiting and error events for the viewer", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const queryClient = createQueryClient();
    queryClient.setQueryData(runRecordKey("biedale", 2), createRunRecord({ status: "running", current_stage: "approve" }));
    const wrapper = createWrapper(queryClient);

    renderHook(() => useRunEvents("biedale", 2), { wrapper });

    act(() => {
      emit("run:waiting", { run_id: "run-1", stage: "approve", message: "等待作者批准" });
      emit("stage:error", { run_id: "run-1", stage: "approve", message: "批准超时" });
    });

    const cached = queryClient.getQueryData<RunRecord>(runRecordKey("biedale", 2));
    expect(cached).toMatchObject({
      status: "failed",
      current_stage: "approve",
      error_message: "批准超时",
      resume_from: "approve"
    });
    expect(cached?.live).toMatchObject({
      waitingMessage: "等待作者批准",
      errorMessage: "批准超时"
    });
  });

  it("reconnects with exponential backoff on stream error", () => {
    vi.useFakeTimers();
    vi.stubGlobal("EventSource", FakeEventSource);
    const queryClient = createQueryClient();
    const wrapper = createWrapper(queryClient);

    const { unmount } = renderHook(() => useRunEvents("biedale", 9), { wrapper });

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

    unmount();
    vi.useRealTimers();
  });

  it("stops reconnecting after the max retry count", () => {
    vi.useFakeTimers();
    vi.stubGlobal("EventSource", FakeEventSource);
    const queryClient = createQueryClient();
    const wrapper = createWrapper(queryClient);

    const { unmount } = renderHook(() => useRunEvents("biedale", 10), { wrapper });

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

function createQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

function createWrapper(queryClient: QueryClient) {
  return ({ children }: PropsWithChildren) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

function emit(type: string, overrides: Record<string, unknown>) {
  FakeEventSource.instances[0].onmessage?.(sse(type, overrides));
}

function sse(type: string, overrides: Record<string, unknown> = {}) {
  return new MessageEvent("message", {
    data: JSON.stringify({
      type,
      book_id: "biedale",
      chapter_no: 2,
      ...overrides
    })
  });
}

function createRunRecord(overrides: Partial<RunRecord> = {}): RunRecord {
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
