import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ImportedProvider } from "@/api/providers";
import { ProviderCard } from "./ProviderCard";

const base: ImportedProvider = {
  id: "p1",
  provider_key: "pk1",
  label: "My Provider",
  base_url: "https://example.test",
  model_id: "gpt-5.5",
  enabled: true,
  active: false,
  api_key: "abcd****1234",
  cc_api_format: "anthropic"
};

describe("ProviderCard", () => {
  it("renders the label and 当前使用 badge when active", () => {
    render(
      <ProviderCard
        provider={{ ...base, active: true }}
        onSwitch={vi.fn()}
        onVerify={vi.fn()}
        onRemove={vi.fn()}
      />
    );
    expect(screen.getByText("My Provider")).toBeInTheDocument();
    expect(screen.getByText("当前使用")).toBeInTheDocument();
  });

  it("calls onSwitch with provider_key when the row is clicked (and not active)", () => {
    const onSwitch = vi.fn();
    render(<ProviderCard provider={base} onSwitch={onSwitch} onVerify={vi.fn()} onRemove={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "切换到 My Provider" }));
    expect(onSwitch).toHaveBeenCalledWith("pk1");
  });

  it("calls onVerify and onRemove with provider_key", () => {
    const onVerify = vi.fn();
    const onRemove = vi.fn();
    render(<ProviderCard provider={base} onSwitch={vi.fn()} onVerify={onVerify} onRemove={onRemove} />);
    fireEvent.click(screen.getByRole("button", { name: "验证 My Provider" }));
    expect(onVerify).toHaveBeenCalledWith("pk1");
    fireEvent.click(screen.getByRole("button", { name: "移除 My Provider" }));
    expect(onRemove).toHaveBeenCalledWith("pk1");
  });
});
