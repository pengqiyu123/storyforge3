import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { BooksPage } from "./BooksPage";

vi.mock("@/hooks/useBooks", () => ({
  useBooks: () => ({
    data: [
      {
        book_id: "book-1",
        title: "我是路人甲",
        genre: "urban",
        platform: "tomato",
        status: "active",
        target_chapters: 100,
        chapter_word_count: 2500,
        current_chapter: 3,
        created_at: "2026-06-08T00:00:00Z",
        updated_at: "2026-06-08T00:00:00Z"
      }
    ],
    isLoading: false,
    error: null
  }),
  useCreateBook: () => ({ mutateAsync: vi.fn(), isPending: false })
}));

describe("BooksPage", () => {
  it("renders book cards from the API hook", () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <BooksPage />
        </MemoryRouter>
      </QueryClientProvider>
    );

    expect(screen.getByRole("heading", { name: "我的小说" })).toBeInTheDocument();
    expect(screen.getByText("我是路人甲")).toBeInTheDocument();
    expect(screen.getByText("3 / 100 章")).toBeInTheDocument();
  });
});
