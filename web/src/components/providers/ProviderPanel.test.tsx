import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ImportedProvider } from "@/api/providers";
import { ProviderPanel } from "./ProviderPanel";

let listState: { data: ImportedProvider[] | undefined; isLoading: boolean; refetch: ReturnType<typeof vi.fn> } = {
  data: [],
  isLoading: false,
  refetch: vi.fn()
};

vi.mock("@/hooks/useProviders", () => ({
  useImportedProviders: () => listState,
  useSwitchProvider: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useVerifyProvider: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useRemoveProvider: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useImportProviders: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useAvailableProviders: () => ({ data: { providers: [], db_available: true }, isLoading: false })
}));

const providers: ImportedProvider[] = [
  { id: "p1", provider_key: "pk1", label: "Alpha", base_url: "https://a.test", model_id: "m", enabled: true, active: true },
  { id: "p2", provider_key: "pk2", label: "Beta", base_url: "https://b.test", model_id: "m", enabled: true, active: false }
];

describe("ProviderPanel", () => {
  beforeEach(() => {
    listState = { data: providers, isLoading: false, refetch: vi.fn() };
  });

  it("renders imported providers and marks the active one", () => {
    render(<ProviderPanel />);
    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("Beta")).toBeInTheDocument();
    expect(screen.getAllByText("当前使用").length).toBeGreaterThan(0);
  });

  it("renders the empty state when there are no providers", () => {
    listState = { data: [], isLoading: false, refetch: vi.fn() };
    render(<ProviderPanel />);
    expect(screen.getByText("尚未导入任何供应商")).toBeInTheDocument();
  });

  it("opens the import dialog on 导入 click", () => {
    render(<ProviderPanel />);
    fireEvent.click(screen.getByRole("button", { name: /^导入$/ }));
    expect(screen.getByText("从 CC-Switch 导入")).toBeInTheDocument();
  });
});
