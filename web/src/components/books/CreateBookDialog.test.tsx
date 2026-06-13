import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CreateBookDialog } from "./CreateBookDialog";

describe("CreateBookDialog", () => {
  it("submits book creation form data", async () => {
    const onCreate = vi.fn().mockResolvedValue(undefined);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={queryClient}>
        <CreateBookDialog onCreate={onCreate} />
      </QueryClientProvider>
    );

    fireEvent.click(screen.getByRole("button", { name: "创建新书" }));
    fireEvent.change(screen.getByLabelText("书名"), { target: { value: "雾都异闻" } });
    fireEvent.change(screen.getByLabelText("类型"), { target: { value: "urban" } });
    fireEvent.change(screen.getByLabelText("目标章节"), { target: { value: "80" } });
    fireEvent.change(screen.getByLabelText("单章字数"), { target: { value: "2600" } });
    fireEvent.click(screen.getByRole("button", { name: "创建" }));

    await waitFor(() =>
      expect(onCreate).toHaveBeenCalledWith({
        title: "雾都异闻",
        genre: "urban",
        platform: "tomato",
        target_chapters: 80,
        chapter_word_count: 2600
      })
    );
  });
});
