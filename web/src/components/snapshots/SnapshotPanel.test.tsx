import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SnapshotMeta } from "@/api/snapshots";
import { SnapshotPanel } from "./SnapshotPanel";

let snapshotListState: { data: SnapshotMeta[] | undefined; isLoading: boolean; refetch: ReturnType<typeof vi.fn> } = {
  data: undefined,
  isLoading: false,
  refetch: vi.fn()
};
const restoreMutateAsync = vi.fn();

vi.mock("@/hooks/useSnapshots", () => ({
  useSnapshotList: () => snapshotListState,
  useSnapshotRestore: () => ({ mutateAsync: restoreMutateAsync, isPending: false })
}));

describe("SnapshotPanel", () => {
  beforeEach(() => {
    snapshotListState = {
      isLoading: false,
      refetch: vi.fn(),
      data: [
        {
          book_id: "lurenjia",
          chapter_no: 5,
          timestamp: "2026-06-10T18:30:00Z",
          file_count: 12,
          path: "20260610T183000000000Z_ch0005.zip"
        }
      ]
    };
    restoreMutateAsync.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders snapshots and restores after confirmation", async () => {
    restoreMutateAsync.mockResolvedValue({ restored_files: ["chapters/0005.md"], count: 1 });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={queryClient}>
        <SnapshotPanel bookId="lurenjia" />
      </QueryClientProvider>
    );

    expect(screen.getByText("版本快照")).toBeInTheDocument();
    expect(screen.getByText(/12 文件/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "回滚第 5 章快照" }));
    expect(screen.getByRole("heading", { name: "确认回滚" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "确认回滚" }));

    await waitFor(() => expect(restoreMutateAsync).toHaveBeenCalledWith("20260610T183000000000Z_ch0005.zip"));
  });

  it("shows empty state when there are no snapshots", () => {
    snapshotListState = { data: [], isLoading: false, refetch: vi.fn() };
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={queryClient}>
        <SnapshotPanel bookId="lurenjia" />
      </QueryClientProvider>
    );

    expect(screen.getByText("暂无快照")).toBeInTheDocument();
    expect(screen.getByText("快照在导出时自动创建（最多保留 5 份）。")).toBeInTheDocument();
  });
});
