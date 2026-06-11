import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AppLayout } from "./AppLayout";

describe("AppLayout", () => {
  it("keeps books navigation active on book detail routes and toggles focus mode", () => {
    localStorage.clear();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/books/demo-book"]}>
          <Routes>
            <Route element={<AppLayout />}>
              <Route path="/books/:id" element={<p>详情页</p>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    expect(screen.getByRole("link", { name: /我的小说/ })).toHaveClass("text-amber-200");
    expect(screen.getByLabelText("开启专注模式")).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(screen.getByLabelText("开启专注模式"));

    expect(screen.getByLabelText("关闭专注模式")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("app-sidebar")).toHaveClass("md:w-0");
  });
});
