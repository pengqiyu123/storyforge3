import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ChangeEvent } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ChapterPipeline, paragraphIndicesToRanges } from "./ChapterPipeline";
import type { ChapterIntent } from "@/api/chapters";
import type { RunRecord } from "@/api/runs";

const planState = vi.hoisted(() => ({ data: null as ChapterIntent | null }));
const runRecordState = vi.hoisted(() => ({ data: null as RunRecord | null }));
const updateMutateAsync = vi.fn();
const cancelMutateAsync = vi.fn();
const rePlanMutateAsync = vi.fn();
const reAuditMutateAsync = vi.fn();
const unexportMutateAsync = vi.fn();
const mutationPending = vi.hoisted(() => ({ rePlan: false, reAudit: false, unexport: false }));
const pipelineEventState = vi.hoisted(() => ({
  current: undefined as
    | ((event: {
        type: string;
        book_id: string;
        chapter_no: number;
        stage?: string;
        message?: string;
        detail?: Record<string, unknown> | null;
      }) => void)
    | undefined
}));

vi.mock("@/hooks/useChapters", () => ({
  useChapterPlanState: () => planState,
  useChapterUpdateText: () => ({ mutateAsync: updateMutateAsync, isPending: false }),
  useRePlan: () => ({ mutateAsync: rePlanMutateAsync, isPending: mutationPending.rePlan }),
  useReAudit: () => ({ mutateAsync: reAuditMutateAsync, isPending: mutationPending.reAudit }),
  useUnexport: () => ({ mutateAsync: unexportMutateAsync, isPending: mutationPending.unexport })
}));

vi.mock("@/hooks/usePipelineEvents", () => ({
  usePipelineEvents: (_bookId?: string, _chapterNo?: number, onEvent?: typeof pipelineEventState.current) => {
    pipelineEventState.current = onEvent;
  }
}));

vi.mock("@/hooks/useRunRecord", () => ({
  useRunRecord: () => runRecordState,
  useCancelRun: () => ({ mutateAsync: cancelMutateAsync, isPending: false })
}));

vi.mock("@/hooks/useRunEvents", () => ({
  useRunEvents: vi.fn()
}));

vi.mock("@/components/editor/ChapterEditor", () => ({
  ChapterEditor: ({
    value,
    readOnly,
    placeholder,
    className,
    onChange
  }: {
    value: string;
    readOnly?: boolean;
    placeholder?: string;
    className?: string;
    onChange?: (value: string) => void;
  }) => (
    <textarea
      aria-label="章节正文"
      data-readonly={String(Boolean(readOnly))}
      className={className}
      placeholder={placeholder}
      value={value}
      readOnly={readOnly}
      onChange={(event: ChangeEvent<HTMLTextAreaElement>) => onChange?.(event.target.value)}
    />
  )
}));

vi.mock("@/components/export/ExportPreviewDialog", () => ({
  ExportPreviewDialog: ({ open }: { open: boolean }) => (open ? <div>导出预览</div> : null)
}));

function renderPipeline(status: string, text = "") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ChapterPipeline
        bookId="lurenjia"
        chapterNo={1}
        result={{ book_id: "lurenjia", chapter_no: 1, status, title: "第1章", text, actual_chars: text.length }}
      />
    </QueryClientProvider>
  );
}

describe("ChapterPipeline (view-only Run Viewer)", () => {
  afterEach(() => {
    planState.data = null;
    runRecordState.data = null;
    updateMutateAsync.mockReset();
    cancelMutateAsync.mockReset();
    rePlanMutateAsync.mockReset();
    reAuditMutateAsync.mockReset();
    unexportMutateAsync.mockReset();
    mutationPending.rePlan = false;
    mutationPending.reAudit = false;
    mutationPending.unexport = false;
    pipelineEventState.current = undefined;
  });

  it("shows the draft text on the default draft tab", () => {
    renderPipeline("drafted", "林默推开门。");
    expect(screen.getByLabelText("章节正文")).toHaveValue("林默推开门。");
  });

  it("switches to the plan view when the 规划 tab is clicked", async () => {
    planState.data = {
      chapter_no: 1,
      goal: "进入副楼",
      outline_node: "夜灯仓纠纷升级",
      arc_context: "",
      must_keep: ["保留巡夜队压力"],
      must_avoid: [],
      style_emphasis: []
    } as ChapterIntent;
    renderPipeline("planned");

    fireEvent.click(screen.getByRole("tab", { name: /规划/ }));

    expect(screen.getByTestId("chapter-plan-panel")).toBeInTheDocument();
    expect(screen.getByText("进入副楼")).toBeInTheDocument();
  });

  it("shows pipeline progress when an agent-driven run starts (no button click)", () => {
    renderPipeline("planned");
    act(() => {
      actPipelineEvent({ type: "pipeline:start", book_id: "lurenjia", chapter_no: 1, stage: "draft", message: "开始起草" });
    });
    expect(screen.getByTestId("pipeline-progress")).toBeInTheDocument();
  });

  it("shows the run viewer above existing view tabs without run trigger actions", () => {
    runRecordState.data = createRunRecord({
      status: "running",
      current_stage: "draft",
      stage_results: {
        plan: {
          stage: "plan",
          status: "completed",
          started_at: "2026-06-15T01:00:00Z",
          finished_at: "2026-06-15T01:00:01Z"
        },
        draft: {
          stage: "draft",
          status: "running",
          started_at: "2026-06-15T01:00:02Z"
        }
      },
      live: {
        stage: "draft",
        progress: { completed: 1, total: 3 },
        streamText: "林默推开门。"
      }
    });

    renderPipeline("planned", "");

    expect(screen.getByTestId("run-track")).toBeInTheDocument();
    expect(screen.getByTestId("live-stage")).toBeInTheDocument();
    expect(screen.getByText("RUNNING")).toBeInTheDocument();
    expect(screen.getByText("由 agent 驱动")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /规划/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /导出/ })).toBeInTheDocument();
    expect(screen.queryByText("运行全流程")).not.toBeInTheDocument();
    expect(screen.queryByText("运行下一阶段")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "取消" })).toBeInTheDocument();
  });

  it("hides cancel when the recovered run is terminal", () => {
    runRecordState.data = createRunRecord({ status: "completed", current_stage: null });

    renderPipeline("exported", "完成。");

    expect(screen.getByTestId("live-stage")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "取消" })).not.toBeInTheDocument();
  });

  it("streams draft text from llm:chunk events into the draft view", () => {
    renderPipeline("planned");
    act(() => {
      actPipelineEvent({ type: "pipeline:start", book_id: "lurenjia", chapter_no: 1, stage: "draft", message: "开始起草" });
      actPipelineEvent({ type: "llm:chunk", book_id: "lurenjia", chapter_no: 1, stage: "draft", detail: { text: "第一段。" } });
      actPipelineEvent({ type: "llm:chunk", book_id: "lurenjia", chapter_no: 1, stage: "draft", detail: { text: "第二段。" } });
    });
    expect(screen.getByLabelText("章节正文")).toHaveValue("第一段。\n\n第二段。");
    expect(screen.getByText("正在生成（流式）…")).toBeInTheDocument();
  });

  it("shows modify-loop buttons by chapter status", () => {
    const exported = renderPipeline("exported", "完成。");
    expect(screen.getByRole("button", { name: "取消导出" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重新审计" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "重新规划" })).not.toBeInTheDocument();
    exported.unmount();

    renderPipeline("needs_review", "待复核。");
    expect(screen.getByRole("button", { name: "重新审计" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重新规划" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "取消导出" })).not.toBeInTheDocument();
  });

  it("calls modify-loop operations from the header buttons", async () => {
    rePlanMutateAsync.mockResolvedValue({ ok: true });
    reAuditMutateAsync.mockResolvedValue({ ok: true });
    unexportMutateAsync.mockResolvedValue({ ok: true });

    const exported = renderPipeline("exported", "完成。");
    fireEvent.click(screen.getByRole("button", { name: "取消导出" }));
    fireEvent.click(screen.getByRole("button", { name: "重新审计" }));

    await waitFor(() => expect(unexportMutateAsync).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(reAuditMutateAsync).toHaveBeenCalledTimes(1));
    exported.unmount();

    renderPipeline("planned", "");
    fireEvent.click(screen.getByRole("button", { name: "重新规划" }));

    await waitFor(() => expect(rePlanMutateAsync).toHaveBeenCalledTimes(1));
  });

  it("disables modify-loop buttons while requests are pending", () => {
    mutationPending.rePlan = true;
    mutationPending.reAudit = true;
    mutationPending.unexport = true;

    const exported = renderPipeline("exported", "完成。");

    expect(screen.getByRole("button", { name: "取消中..." })).toBeDisabled();
    expect(screen.getByRole("button", { name: "审计中..." })).toBeDisabled();
    exported.unmount();

    renderPipeline("needs_review", "待复核。");
    expect(screen.getByRole("button", { name: "规划中..." })).toBeDisabled();
  });

  it("shows modify-loop operation errors", async () => {
    reAuditMutateAsync.mockRejectedValue(new Error("服务不可用"));

    renderPipeline("drafted", "林默推开门。");
    fireEvent.click(screen.getByRole("button", { name: "重新审计" }));

    expect(await screen.findByText("重新审计失败: 服务不可用")).toBeInTheDocument();
  });

  it("edits and saves the draft text", async () => {
    updateMutateAsync.mockResolvedValue({ ok: true });
    renderPipeline("drafted", "林默推开门。");

    fireEvent.click(screen.getByRole("button", { name: /编辑/ }));
    fireEvent.change(screen.getByLabelText("章节正文"), { target: { value: "林默推开门，补一句。" } });
    fireEvent.click(screen.getByRole("button", { name: /保存/ }));

    await waitFor(() =>
      expect(updateMutateAsync).toHaveBeenCalledWith(expect.objectContaining({ chapterNo: 1, text: "林默推开门，补一句。" }))
    );
  });

  it("never disables a stage tab (view tabs are always clickable)", () => {
    renderPipeline("exported", "完成。");
    // Every stage is viewable regardless of completion — none should be disabled.
    for (const label of ["规划", "起草", "审计", "修订", "批准", "导出"]) {
      expect(screen.getByRole("tab", { name: new RegExp(label) })).toBeEnabled();
    }
  });

  it("converts paragraph indices to character ranges", () => {
    expect(paragraphIndicesToRanges("第一段。\n\n第二段。\n\n第三段。", [1, 2])).toEqual([
      { from: 6, to: 10 },
      { from: 12, to: 16 }
    ]);
  });
});

function actPipelineEvent(event: {
  type: string;
  book_id: string;
  chapter_no: number;
  stage?: string;
  message?: string;
  detail?: Record<string, unknown> | null;
}) {
  if (!pipelineEventState.current) {
    throw new Error("pipeline event callback not registered");
  }
  pipelineEventState.current(event);
}

function createRunRecord(overrides: Partial<RunRecord> = {}): RunRecord {
  return {
    run_id: "run-1",
    book_id: "lurenjia",
    chapter_no: 1,
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
