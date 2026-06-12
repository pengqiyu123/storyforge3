import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ChangeEvent } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ChapterPipeline, paragraphIndicesToRanges } from "./ChapterPipeline";

const auditMutateAsync = vi.fn();
const reviseMutateAsync = vi.fn();
const pendingState = vi.hoisted(() => ({
  audit: false,
  revise: false,
  runFull: false
}));
const toastMocks = vi.hoisted(() => ({
  info: vi.fn(),
  error: vi.fn(),
  success: vi.fn()
}));

vi.mock("sonner", () => ({
  toast: {
    info: toastMocks.info,
    success: toastMocks.success,
    error: toastMocks.error
  }
}));

vi.mock("@/components/editor/ChapterEditor", () => ({
  ChapterEditor: ({
    value,
    readOnly,
    placeholder,
    className,
    onChange,
    highlights,
    scrollToOffset
  }: {
    value: string;
    readOnly?: boolean;
    placeholder?: string;
    className?: string;
    onChange?: (value: string) => void;
    highlights?: unknown[];
    scrollToOffset?: number;
  }) => (
    <textarea
      aria-label="章节文本预览"
      data-readonly={String(Boolean(readOnly))}
      data-highlights={JSON.stringify(highlights ?? [])}
      data-scroll-to-offset={String(scrollToOffset ?? "")}
      readOnly={readOnly}
      className={className}
      placeholder={placeholder}
      value={value}
      onChange={(event: ChangeEvent<HTMLTextAreaElement>) => onChange?.(event.target.value)}
    />
  )
}));

vi.mock("@/components/export/ExportPreviewDialog", () => ({
  ExportPreviewDialog: ({ open }: { open: boolean }) => (open ? <div>导出预览</div> : null)
}));

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

vi.mock("@/hooks/usePipelineEvents", () => ({
  usePipelineEvents: (_bookId?: string, _chapterNo?: number, onEvent?: typeof pipelineEventState.current) => {
    pipelineEventState.current = onEvent;
  }
}));

vi.mock("@/hooks/useChapters", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/useChapters")>("@/hooks/useChapters");
  return {
    ...actual,
    useChapterAudit: () => ({ mutateAsync: auditMutateAsync, isPending: pendingState.audit }),
    useChapterRevise: () => ({ mutateAsync: reviseMutateAsync, isPending: pendingState.revise }),
    useRunFullPipeline: () => ({ mutateAsync: vi.fn(), isPending: pendingState.runFull })
  };
});

describe("ChapterPipeline", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    pendingState.audit = false;
    pendingState.revise = false;
    pendingState.runFull = false;
    pipelineEventState.current = undefined;
    auditMutateAsync.mockReset();
    reviseMutateAsync.mockReset();
    toastMocks.info.mockReset();
    toastMocks.error.mockReset();
    toastMocks.success.mockReset();
  });

  it("runs plan action and displays text preview", async () => {
    const onPlan = vi.fn().mockResolvedValue({ chapter_no: 1, goal: "进入副楼" });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={queryClient}>
        <ChapterPipeline
          bookId="lurenjia"
          chapterNo={1}
          result={{ book_id: "lurenjia", chapter_no: 1, status: "drafted", title: "第1章", text: "林默推开门。" }}
          onPlan={onPlan}
        />
      </QueryClientProvider>
    );

    expect(screen.getByLabelText("章节文本预览")).toHaveTextContent("林默推开门。");
    expect(screen.getByLabelText("章节文本预览")).toHaveAttribute("data-readonly", "true");
    expect(screen.getByText("5 字")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /规划/ }));

    await waitFor(() => expect(onPlan).toHaveBeenCalledWith(1));
  });

  it("shows the latest audit result after running audit", async () => {
    auditMutateAsync.mockResolvedValueOnce({
      chapter_no: 1,
      passed: false,
      blocking_issues: ["golden_three_hook"],
      warnings: [],
      info: [],
      rule_results: [
        {
          rule_id: "golden_three_hook",
          passed: false,
          severity: "BLOCKING",
          category: "STRUCTURE",
          message: "前三段缺少有效钩子",
          detail: { paragraph_indices: [1], snippet: "第二段太平。" }
        }
      ]
    });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={queryClient}>
        <ChapterPipeline
          bookId="lurenjia"
          chapterNo={1}
          result={{ book_id: "lurenjia", chapter_no: 1, status: "audited", title: "第1章", text: "第一段。\n\n第二段。" }}
        />
      </QueryClientProvider>
    );

    fireEvent.click(screen.getByRole("button", { name: /审计/ }));

    await waitFor(() => expect(screen.getByText("审计未通过")).toBeInTheDocument());
    expect(screen.getByText("golden_three_hook")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /定位 golden_three_hook/ }));
    await waitFor(() =>
      expect(screen.getByLabelText("章节文本预览")).toHaveAttribute("data-highlights", JSON.stringify([{ from: 6, to: 10, severity: "BLOCKING" }]))
    );
    expect(screen.getByLabelText("章节文本预览")).toHaveAttribute("data-scroll-to-offset", "6");
  });

  it("shows revision diff after revise and clears it on a later audit", async () => {
    reviseMutateAsync.mockResolvedValueOnce({
      book_id: "lurenjia",
      chapter_no: 1,
      status: "revised",
      title: "第1章",
      text: "修订后正文。",
      revision_diff: {
        unit: "paragraph",
        summary: {
          changed_blocks: 1,
          added_blocks: 0,
          removed_blocks: 0,
          before_chars: 6,
          after_chars: 6
        },
        blocks: [{ kind: "replace", before_text: "修订前正文。", after_text: "修订后正文。" }]
      }
    });
    auditMutateAsync.mockResolvedValueOnce({
      chapter_no: 1,
      passed: true,
      blocking_issues: [],
      warnings: [],
      info: [],
      rule_results: []
    });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={queryClient}>
        <ChapterPipeline
          bookId="lurenjia"
          chapterNo={1}
          result={{ book_id: "lurenjia", chapter_no: 1, status: "audited", title: "第1章", text: "修订前正文。" }}
        />
      </QueryClientProvider>
    );

    fireEvent.click(screen.getByRole("button", { name: /修订/ }));

    await waitFor(() => expect(screen.getByText("修订变更")).toBeInTheDocument());
    const diffPanel = screen.getByTestId("revision-diff-panel");
    expect(within(diffPanel).getByText("修订前正文。")).toBeInTheDocument();
    expect(within(diffPanel).getByText("修订后正文。")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /审计/ }));

    await waitFor(() => expect(screen.queryByText("修订变更")).not.toBeInTheDocument());
  });

  it("edits, saves, and sends the current content hash", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          ok: true,
          data: {
            book_id: "lurenjia",
            chapter_no: 1,
            status: "needs_review",
            title: "第1章",
            text: "林默推开门，补上一句。",
            content_hash: "newhash1",
            actual_chars: 11,
            error: null
          },
          error: null
        })
      )
    );
    vi.stubGlobal("fetch", fetchMock);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={queryClient}>
        <ChapterPipeline
          bookId="lurenjia"
          chapterNo={1}
          result={{
            book_id: "lurenjia",
            chapter_no: 1,
            status: "drafted",
            title: "第1章",
            text: "林默推开门。",
            content_hash: "oldhash1",
            actual_chars: 5
          }}
        />
      </QueryClientProvider>
    );

    fireEvent.click(screen.getByRole("button", { name: "编辑" }));
    const editor = screen.getByLabelText("章节文本预览");
    expect(editor).toHaveAttribute("data-readonly", "false");

    fireEvent.change(editor, { target: { value: "林默推开门，补上一句。" } });

    expect(screen.getByText("未保存的修改")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /保存/ }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/books/lurenjia/chapters/1/text",
        expect.objectContaining({
          method: "PUT",
          body: JSON.stringify({
            text: "林默推开门，补上一句。",
            expected_hash: "oldhash1"
          })
        })
      )
    );
  });

  it("discards unsaved edits", () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={queryClient}>
        <ChapterPipeline
          bookId="lurenjia"
          chapterNo={1}
          result={{ book_id: "lurenjia", chapter_no: 1, status: "drafted", title: "第1章", text: "林默推开门。", content_hash: "oldhash1" }}
        />
      </QueryClientProvider>
    );

    fireEvent.click(screen.getByRole("button", { name: "编辑" }));
    fireEvent.change(screen.getByLabelText("章节文本预览"), { target: { value: "临时修改。" } });

    fireEvent.click(screen.getByRole("button", { name: "放弃修改" }));

    expect(screen.getByLabelText("章节文本预览")).toHaveValue("林默推开门。");
    expect(screen.getByLabelText("章节文本预览")).toHaveAttribute("data-readonly", "true");
  });

  it("saves with ctrl+s and keeps edit mode on conflicts", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          ok: false,
          data: null,
          error: { code: "CONTENT_CONFLICT", message: "章节内容已被修改，请刷新后重试" }
        }),
        { status: 409 }
      )
    );
    vi.stubGlobal("fetch", fetchMock);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={queryClient}>
        <ChapterPipeline
          bookId="lurenjia"
          chapterNo={1}
          result={{ book_id: "lurenjia", chapter_no: 1, status: "drafted", title: "第1章", text: "林默推开门。", content_hash: "oldhash1" }}
        />
      </QueryClientProvider>
    );

    fireEvent.click(screen.getByRole("button", { name: "编辑" }));
    fireEvent.change(screen.getByLabelText("章节文本预览"), { target: { value: "林默推开门，补上一句。" } });
    fireEvent.keyDown(window, { key: "s", ctrlKey: true });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(toastMocks.error).toHaveBeenCalledWith("内容已被修改，请刷新"));
    expect(screen.getByLabelText("章节文本预览")).toHaveAttribute("data-readonly", "false");
  });

  it("converts paragraph indices to character ranges", () => {
    expect(paragraphIndicesToRanges("第一段。\n\n第二段。\n\n第三段。", [1, 2])).toEqual([
      { from: 6, to: 10 },
      { from: 12, to: 16 }
    ]);
  });

  it("opens export preview from the preview button", async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={queryClient}>
        <ChapterPipeline
          bookId="lurenjia"
          chapterNo={1}
          result={{ book_id: "lurenjia", chapter_no: 1, status: "drafted", title: "第1章", text: "林默推开门。", content_hash: "oldhash1" }}
        />
      </QueryClientProvider>
    );

    fireEvent.click(screen.getByRole("button", { name: "预览" }));

    await waitFor(() => expect(screen.getByText("导出预览")).toBeInTheDocument());
  });

  it("shows pipeline progress when busy after pipeline start event", () => {
    pendingState.audit = true;
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const onPlan = vi.fn(() => new Promise(() => undefined));

    render(
      <QueryClientProvider client={queryClient}>
        <ChapterPipeline
          bookId="lurenjia"
          chapterNo={1}
          result={{ book_id: "lurenjia", chapter_no: 1, status: "drafted", title: "第1章", text: "林默推开门。" }}
          onPlan={onPlan}
        />
      </QueryClientProvider>
    );

    act(() => {
      actPipelineEvent({ type: "pipeline:start", book_id: "lurenjia", chapter_no: 1, stage: "起草", message: "开始起草" });
    });

    expect(screen.getByTestId("pipeline-progress")).toBeInTheDocument();
    expect(screen.getByText("正在起草...")).toBeInTheDocument();
  });

  it("updates chunk progress from sse events", () => {
    pendingState.audit = true;
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const onPlan = vi.fn(() => new Promise(() => undefined));

    render(
      <QueryClientProvider client={queryClient}>
        <ChapterPipeline
          bookId="lurenjia"
          chapterNo={1}
          result={{ book_id: "lurenjia", chapter_no: 1, status: "drafted", title: "第1章", text: "林默推开门。" }}
          onPlan={onPlan}
        />
      </QueryClientProvider>
    );

    act(() => {
      actPipelineEvent({ type: "pipeline:start", book_id: "lurenjia", chapter_no: 1, stage: "起草", message: "开始起草" });
      actPipelineEvent({
        type: "llm:progress",
        book_id: "lurenjia",
        chapter_no: 1,
        stage: "draft",
        detail: { completed: 3, total: 5 }
      });
    });

    expect(screen.getByText("3/5 段")).toBeInTheDocument();
    expect(screen.getByText("正在生成第 3/5 段")).toBeInTheDocument();
    expect(screen.getByTestId("pipeline-progress-bar")).toHaveStyle({ width: "60%" });
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
