import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Book } from "@/api/books";
import { BookDetailPage } from "./BookDetailPage";

let bookQuery: { data: Book | null; isLoading: boolean; error: unknown } = {
  data: {
    book_id: "lurenjia",
    title: "我是路人甲",
    genre: "urban",
    platform: "tomato",
    status: "active",
    target_chapters: 100,
    chapter_word_count: 2500,
    current_chapter: 3,
    created_at: "2026-06-08T00:00:00Z",
    updated_at: "2026-06-08T00:00:00Z"
  },
  isLoading: false,
  error: null
};

vi.mock("@/hooks/useBooks", () => ({
  useBook: () => bookQuery
}));

vi.mock("@/hooks/useWorld", () => ({
  useWorld: () => ({ data: null, isLoading: false, error: null }),
  useBuildWorld: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateWorld: () => ({ mutateAsync: vi.fn(), isPending: false })
}));

vi.mock("@/hooks/useCharacters", () => ({
  useCharacters: () => ({ data: [], isLoading: false, error: null }),
  useCharacterRelationships: () => ({ data: [], isLoading: false }),
  useCreateCharacter: () => ({ mutateAsync: vi.fn(), isPending: false })
}));

vi.mock("@/hooks/useVolumes", () => ({
  useVolumes: () => ({ data: [], isLoading: false, error: null }),
  usePlanVolumes: () => ({ mutateAsync: vi.fn(), isPending: false })
}));

describe("BookDetailPage", () => {
  beforeEach(() => {
    bookQuery = {
      data: {
        book_id: "lurenjia",
        title: "我是路人甲",
        genre: "urban",
        platform: "tomato",
        status: "active",
        target_chapters: 100,
        chapter_word_count: 2500,
        current_chapter: 3,
        created_at: "2026-06-08T00:00:00Z",
        updated_at: "2026-06-08T00:00:00Z"
      },
      isLoading: false,
      error: null
    };
  });

  it("renders the seven book detail tabs", () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/books/lurenjia"]}>
          <Routes>
            <Route path="/books/:id" element={<BookDetailPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    expect(screen.getByRole("heading", { name: "我是路人甲" })).toBeInTheDocument();
    for (const tab of ["概览", "世界观", "角色", "卷规划", "章节", "真相", "快照"]) {
      expect(screen.getByRole("tab", { name: tab })).toBeInTheDocument();
    }
  });

  it("uses skeleton loading instead of a plain loading sentence", () => {
    bookQuery = { data: null, isLoading: true, error: null };
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/books/lurenjia"]}>
          <Routes>
            <Route path="/books/:id" element={<BookDetailPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    expect(screen.queryByText("正在读取书籍...")).not.toBeInTheDocument();
    expect(screen.getByTestId("book-detail-loading")).toBeInTheDocument();
  });
});
