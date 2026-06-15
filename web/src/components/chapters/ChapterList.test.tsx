import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Book } from "@/api/books";
import type { BookReconciliation } from "@/api/reconcile";
import type { VolumeOutline } from "@/api/volumes";
import { ChapterList } from "./ChapterList";

let reconciliation: BookReconciliation | undefined;
let volumes: VolumeOutline[] | undefined;

vi.mock("@/hooks/useReconcile", () => ({
  useReconcile: () => ({ data: reconciliation, isLoading: false, error: null }),
  useInvalidateReconcile: () => vi.fn()
}));

vi.mock("@/hooks/useVolumes", () => ({
  useVolumes: () => ({ data: volumes, isLoading: false, error: null })
}));

vi.mock("./ChapterPipeline", () => ({
  ChapterPipeline: ({ chapterNo, result }: { chapterNo: number; result?: { status?: string } | null }) => (
    <div>
      第 {chapterNo} 章详情 {result?.status}
    </div>
  )
}));

const book: Book = {
  book_id: "biedale",
  title: "别打了",
  genre: "都市",
  platform: "tomato",
  status: "active",
  target_chapters: 100,
  chapter_word_count: 2500,
  current_chapter: 2,
  created_at: "2026-06-14T00:00:00Z",
  updated_at: "2026-06-14T00:00:00Z"
};

describe("ChapterList", () => {
  beforeEach(() => {
    reconciliation = biedaleReconciliation();
    volumes = undefined;
  });

  it("renders real reconciled chapters, inconsistent badges, reasons, and one next-chapter indicator", () => {
    renderList();

    expect(screen.getByText("已发现章节产物 4 章 · 最高第 4 章 · ⚠ 2 章数据不一致")).toBeInTheDocument();
    expect(screen.queryByText("真实产物 4 章")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /第 1 章/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /第 2 章/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /第 3 章/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /第 4 章/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /第 5 章/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /第 6 章/ })).not.toBeInTheDocument();

    expect(screen.getAllByText("数据不一致")).toHaveLength(2);
    expect(screen.getAllByText("孤儿产物：有 Truth/导出但无正文")).toHaveLength(2);
    expect(screen.getByText("⚠ 存在数据不一致（第 3、4 章），请先检查后再继续生产")).toBeInTheDocument();
    expect(screen.queryByText("下一章：第 5 章")).not.toBeInTheDocument();
    expect(screen.queryByText("由 agent 触发生产")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /第 3 章/ }));
    const expanded = screen.getByTestId("chapter-3-inconsistent-reasons");
    expect(within(expanded).getByText("已导出但无状态记录")).toBeInTheDocument();
    expect(within(expanded).getByText("已导出但无正文文件")).toBeInTheDocument();
    expect(within(expanded).getByText("有 Truth 但无状态记录")).toBeInTheDocument();
    expect(screen.getByText(/第 3 章详情 needs_review/)).toBeInTheDocument();
  });

  it("shows produced-stage checks from reconciliation artifacts without status probes", () => {
    renderList();

    const chapter2 = screen.getByTestId("chapter-card-2");
    expect(within(chapter2).getByText("规划")).toHaveAttribute("data-produced", "true");
    expect(within(chapter2).getByText("正文")).toHaveAttribute("data-produced", "true");
    expect(within(chapter2).getByText("Truth")).toHaveAttribute("data-produced", "true");
    expect(within(chapter2).getByText("导出")).toHaveAttribute("data-produced", "true");
  });

  it("shows only chapter one next indicator for a book with no artifacts", () => {
    reconciliation = {
      book_id: "empty-book",
      chapters: [],
      inconsistent_count: 0,
      max_chapter: 0,
      valid_chapter_count: 0,
      highest_contiguous_chapter: 0,
      next_writable_chapter_no: 1,
      has_blocking_inconsistency: false
    };

    renderList({ ...book, book_id: "empty-book", current_chapter: 0 });

    expect(screen.queryByTestId(/chapter-card-/)).not.toBeInTheDocument();
    expect(screen.getByText("下一章：第 1 章")).toBeInTheDocument();
    expect(screen.getByText("尚未产生章节产物，由 agent/API 启动生产")).toBeInTheDocument();
  });

  it("does not render all-empty gap chapters returned inside the reconciliation range", () => {
    reconciliation = {
      book_id: "gap-book",
      inconsistent_count: 0,
      max_chapter: 4,
      valid_chapter_count: 2,
      highest_contiguous_chapter: 1,
      next_writable_chapter_no: 2,
      has_blocking_inconsistency: false,
      chapters: [
        chapter(1, { has_text: true, validity: "valid" }),
        chapter(2, { validity: "empty" }),
        chapter(4, { has_text: true, validity: "valid" })
      ]
    };

    renderList({ ...book, book_id: "gap-book" });

    expect(screen.getByTestId("chapter-card-1")).toBeInTheDocument();
    expect(screen.queryByTestId("chapter-card-2")).not.toBeInTheDocument();
    expect(screen.getByTestId("chapter-card-4")).toBeInTheDocument();
    expect(screen.getByText("下一章：第 2 章")).toBeInTheDocument();
  });

  it("marks partial chapters without treating them as blocking inconsistencies", () => {
    reconciliation = {
      book_id: "partial-book",
      inconsistent_count: 0,
      max_chapter: 2,
      valid_chapter_count: 1,
      highest_contiguous_chapter: 1,
      next_writable_chapter_no: 2,
      has_blocking_inconsistency: false,
      chapters: [chapter(1, { has_text: true, validity: "valid" }), chapter(2, { has_plan: true, validity: "partial" })]
    };

    renderList({ ...book, book_id: "partial-book" });

    expect(screen.getByTestId("chapter-card-2")).toBeInTheDocument();
    expect(screen.getByText("部分产物")).toBeInTheDocument();
    expect(screen.getByText("下一章：第 2 章")).toBeInTheDocument();
  });

  it("groups chapters by existing volume outlines", () => {
    volumes = [
      volume(1, "误入前线", 2),
      volume(2, "翻译官上岗", 2)
    ];

    renderList();

    expect(screen.getByText("第 1 卷：误入前线")).toBeInTheDocument();
    expect(screen.getByText("第 2 卷：翻译官上岗")).toBeInTheDocument();
    const secondVolume = screen.getByTestId("chapter-volume-2");
    expect(within(secondVolume).getByRole("button", { name: /第 3 章/ })).toBeInTheDocument();
    expect(within(secondVolume).getByRole("button", { name: /第 4 章/ })).toBeInTheDocument();
  });
});

function renderList(targetBook: Book = book) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ChapterList book={targetBook} />
    </QueryClientProvider>
  );
}

function biedaleReconciliation(): BookReconciliation {
  return {
    book_id: "biedale",
    inconsistent_count: 2,
    max_chapter: 4,
    valid_chapter_count: 2,
    highest_contiguous_chapter: 2,
    next_writable_chapter_no: 3,
    has_blocking_inconsistency: true,
    chapters: [
      chapter(1, { has_text: true, has_plan: true, has_truth: true, has_export: true, has_state: true, state_status: "exported", validity: "valid" }),
      chapter(2, { has_text: true, has_plan: true, has_truth: true, has_export: true, has_state: true, state_status: "drafted", validity: "valid" }),
      chapter(3, {
        has_truth: true,
        has_export: true,
        validity: "orphan",
        status: "inconsistent",
        inconsistent_reasons: ["export_without_state", "export_without_text", "truth_without_state"]
      }),
      chapter(4, {
        has_truth: true,
        has_export: true,
        validity: "orphan",
        status: "inconsistent",
        inconsistent_reasons: ["export_without_state", "export_without_text", "truth_without_state"]
      })
    ]
  };
}

function chapter(
  chapter_no: number,
  overrides: Partial<BookReconciliation["chapters"][number]>
): BookReconciliation["chapters"][number] {
  return {
    chapter_no,
    has_text: false,
    has_plan: false,
    has_truth: false,
    has_export: false,
    has_state: false,
    has_run: false,
    state_status: null,
    status: "consistent",
    validity: "empty",
    inconsistent_reasons: [],
    ...overrides
  };
}

function volume(volume_no: number, title: string, chapter_count: number): VolumeOutline {
  return {
    book_id: "biedale",
    volume_no,
    title,
    chapter_count,
    synopsis: "",
    key_scenes: [],
    rhythm_curve: []
  };
}
