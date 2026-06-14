import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AvailableProvidersResponse, ImportProvidersResponse } from "@/api/providers";
import { CCImportDialog } from "./CCImportDialog";

let availableState: { data: AvailableProvidersResponse | undefined; isLoading: boolean } = {
  data: undefined,
  isLoading: false
};
const importMutateAsync = vi.fn();

vi.mock("@/hooks/useProviders", () => ({
  useAvailableProviders: () => availableState,
  useImportProviders: () => ({ mutateAsync: importMutateAsync, isPending: false })
}));

const one = {
  id: "cc-one",
  label: "One",
  provider_key: "cc-one",
  base_url: "https://one.test",
  has_api_key: true,
  api_key_preview: "abcd****1234",
  model_id: "gpt-5.5",
  cc_is_current: false
};
const two = { ...one, id: "cc-two", label: "Two", provider_key: "cc-two" };
const noKey = {
  ...one,
  id: "cc-empty",
  label: "No Key",
  provider_key: "cc-empty",
  has_api_key: false,
  api_key_preview: ""
};

describe("CCImportDialog", () => {
  beforeEach(() => {
    availableState = { data: { providers: [one, two], db_available: true }, isLoading: false };
    importMutateAsync.mockReset();
    importMutateAsync.mockResolvedValue({ imported: [], active_provider_key: null } as ImportProvidersResponse);
  });

  it("disables 导入 when nothing is selected, enables after 全选", () => {
    render(<CCImportDialog open={true} onOpenChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: /^导入\(/ })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: /全选/ }));
    expect(screen.getByRole("button", { name: /^导入\(/ })).toBeEnabled();
  });

  it("shows the db-missing message when db_available is false", () => {
    availableState = { data: { providers: [], db_available: false }, isLoading: false };
    render(<CCImportDialog open={true} onOpenChange={vi.fn()} />);
    expect(screen.getByText(/未找到 CC-Switch 数据库/)).toBeInTheDocument();
  });

  it("imports the selected ids and closes the dialog", async () => {
    const onOpenChange = vi.fn();
    render(<CCImportDialog open={true} onOpenChange={onOpenChange} />);
    fireEvent.click(screen.getByRole("button", { name: /全选/ }));
    fireEvent.click(screen.getByRole("button", { name: /^导入\(/ }));
    await waitFor(() => expect(importMutateAsync).toHaveBeenCalledWith(["cc-one", "cc-two"]));
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it("disables no-key providers and excludes them from 全选", async () => {
    availableState = { data: { providers: [one, noKey], db_available: true }, isLoading: false };
    render(<CCImportDialog open={true} onOpenChange={vi.fn()} />);

    expect(screen.getByRole("button", { name: /No Key/ })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: /全选/ }));
    fireEvent.click(screen.getByRole("button", { name: /^导入\(/ }));

    await waitFor(() => expect(importMutateAsync).toHaveBeenCalledWith(["cc-one"]));
  });
});
