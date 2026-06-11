import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DashboardPage } from "./DashboardPage";

vi.mock("@/hooks/useBooks", () => ({
  useBooks: () => ({
    data: [
      {
        book_id: "older-book",
        title: "旧案笔记",
        genre: "urban",
        platform: "tomato",
        status: "paused",
        target_chapters: 80,
        chapter_word_count: 2200,
        current_chapter: 8,
        created_at: "2026-06-01T00:00:00Z",
        updated_at: "2026-06-02T00:00:00Z"
      },
      {
        book_id: "active-book",
        title: "雾港夜巡",
        genre: "suspense",
        platform: "tomato",
        status: "active",
        target_chapters: 120,
        chapter_word_count: 2500,
        current_chapter: 21,
        created_at: "2026-06-07T00:00:00Z",
        updated_at: "2026-06-08T12:00:00Z"
      }
    ],
    isLoading: false,
    error: null
  })
}));

vi.mock("@/hooks/useHealth", () => ({
  useHealth: () => ({
    data: { status: "ok", default_model: "gpt-4o", books_dir: "books" },
    isLoading: false
  }),
  useProviders: () => ({
    data: [
      {
        id: "codex",
        provider_key: "codex",
        label: "Codex 直连中转",
        base_url: "https://api.vip1129.cc/v1",
        model_id: "",
        enabled: true,
        source: "cc-switch",
        cc_last_verified_model: "gpt-5.5"
      }
    ],
    isLoading: false
  })
}));

describe("DashboardPage", () => {
  it("renders provider status, recent activity, and active-book quick actions", () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <DashboardPage />
        </MemoryRouter>
      </QueryClientProvider>
    );

    expect(screen.getByText("Provider 状态")).toBeInTheDocument();
    expect(screen.getByText("Codex 直连中转")).toBeInTheDocument();
    expect(screen.getByText("中转站默认")).toBeInTheDocument();
    expect(screen.getByText("已验证：gpt-5.5")).toBeInTheDocument();
    expect(screen.queryByText("gpt-4o")).not.toBeInTheDocument();
    expect(screen.getByText("最近活动")).toBeInTheDocument();
    expect(screen.getAllByText("雾港夜巡")[0]).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /构建世界观/ })).toHaveAttribute("href", "/books/active-book?tab=world");
    expect(screen.getByRole("link", { name: /运行全流程/ })).toHaveAttribute("href", "/books/active-book?tab=chapters");
  });
});
