import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { TruthData } from "@/api/truth";
import { TruthPanel } from "./TruthPanel";

let truthQueryState: { data: TruthData[] | undefined; isLoading: boolean } = {
  data: undefined,
  isLoading: false
};

vi.mock("@/hooks/useTruth", () => ({
  useTruthHistory: () => truthQueryState
}));

describe("TruthPanel", () => {
  beforeEach(() => {
    truthQueryState = {
      isLoading: false,
      data: [
        {
          chapter_no: 1,
          source: "runtime_native",
          fact_assertions: ["林默发现存在感异常。"],
          character_updates: [{ summary: "林默开始怀疑检测中心。" }],
          relationship_updates: [],
          hook_updates: [{ summary: "副楼门后仍有异常声。" }],
          irreversible_facts: [],
          notes: ["继续观察许青。"]
        },
        {
          chapter_no: 2,
          source: "runtime_native",
          fact_assertions: ["林默进入检测中心。"],
          character_updates: [],
          relationship_updates: [],
          hook_updates: [],
          irreversible_facts: ["许青知道残痕机制。"],
          notes: []
        }
      ]
    };
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders grouped truth data and filters by chapter", () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={queryClient}>
        <TruthPanel bookId="lurenjia" />
      </QueryClientProvider>
    );

    expect(screen.getByText("真相数据")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "第 1 章" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "第 2 章" })).toBeInTheDocument();
    expect(screen.getByText("林默发现存在感异常。")).toBeInTheDocument();
    expect(screen.getByText("许青知道残痕机制。")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "第 2 章" }));

    expect(screen.queryByText("林默发现存在感异常。")).not.toBeInTheDocument();
    expect(screen.getByText("许青知道残痕机制。")).toBeInTheDocument();
  });

  it("filters truth entries by search query and shows empty state", () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    const { rerender } = render(
      <QueryClientProvider client={queryClient}>
        <TruthPanel bookId="lurenjia" />
      </QueryClientProvider>
    );

    fireEvent.change(screen.getByPlaceholderText("搜索事实、角色、钩子"), { target: { value: "许青" } });

    expect(screen.queryByText("林默发现存在感异常。")).not.toBeInTheDocument();
    expect(screen.getByText("许青知道残痕机制。")).toBeInTheDocument();

    truthQueryState = { data: [], isLoading: false };
    rerender(
      <QueryClientProvider client={queryClient}>
        <TruthPanel bookId="lurenjia" />
      </QueryClientProvider>
    );

    expect(screen.getByText("暂无真相数据。运行章节管线后，真相会在 audit 通过后自动提取。")).toBeInTheDocument();
  });
});
