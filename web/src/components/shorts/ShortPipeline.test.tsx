import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ShortPipeline } from "./ShortPipeline";

const planMutateAsync = vi.fn();
const runFullMutateAsync = vi.fn();

vi.mock("@/components/editor/ChapterEditor", () => ({
  ChapterEditor: ({ value, readOnly, placeholder }: { value: string; readOnly?: boolean; placeholder?: string }) => (
    <div aria-label="短篇文本预览" data-readonly={String(Boolean(readOnly))}>
      {value || placeholder}
    </div>
  )
}));

vi.mock("@/hooks/useShorts", () => ({
  useShortPlan: () => ({ mutateAsync: planMutateAsync, isPending: false }),
  useShortDraft: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useShortAudit: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useShortRevise: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useShortExport: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useShortRunFull: () => ({ mutateAsync: runFullMutateAsync, isPending: false })
}));

describe("ShortPipeline", () => {
  it("renders five short story pipeline actions and readonly preview", () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={queryClient}>
        <ShortPipeline
          bookId="story-night-shift"
          result={{ book_id: "story-night-shift", status: "drafted", text: "林默推开便利店的门。", error: null }}
        />
      </QueryClientProvider>
    );

    for (const label of ["构思", "起草", "审计", "修订", "导出"]) {
      expect(screen.getByRole("button", { name: new RegExp(label) })).toBeInTheDocument();
    }
    expect(screen.getByRole("button", { name: /构思/ })).toHaveClass("bg-amber-300");
    expect(screen.getByRole("button", { name: /起草/ })).toHaveClass("bg-amber-300");
    expect(screen.getByRole("button", { name: /审计/ })).toHaveClass("border");
    expect(screen.getByLabelText("短篇文本预览")).toHaveAttribute("data-readonly", "true");
    expect(screen.getByText("林默推开便利店的门。")).toBeInTheDocument();
  });

  it("runs plan and full pipeline actions", async () => {
    planMutateAsync.mockResolvedValueOnce({ book_id: "story-night-shift", opening: "异常开篇" });
    runFullMutateAsync.mockResolvedValueOnce({ book_id: "story-night-shift", status: "exported", text: "完成正文" });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={queryClient}>
        <ShortPipeline bookId="story-night-shift" result={{ book_id: "story-night-shift", status: "empty", text: "", error: null }} />
      </QueryClientProvider>
    );

    fireEvent.click(screen.getByRole("button", { name: /构思/ }));
    fireEvent.click(screen.getByRole("button", { name: /一键运行/ }));

    await waitFor(() => expect(planMutateAsync).toHaveBeenCalled());
    await waitFor(() => expect(runFullMutateAsync).toHaveBeenCalled());
  });
});
