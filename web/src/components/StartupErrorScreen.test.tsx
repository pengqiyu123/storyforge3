import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StartupErrorScreen } from "./StartupErrorScreen";

const { openPathMock } = vi.hoisted(() => ({
  openPathMock: vi.fn()
}));

vi.mock("@tauri-apps/plugin-opener", () => ({
  openPath: openPathMock
}));

vi.mock("@tauri-apps/api/path", () => ({
  dataDir: vi.fn(async () => "C:/Users/pengq/AppData/Roaming"),
  join: vi.fn(async (...parts: string[]) => parts.join("/"))
}));

describe("StartupErrorScreen", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    openPathMock.mockReset();
  });

  it("shows startup diagnostics and reloads on retry", () => {
    const reloadMock = vi.fn();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { reload: reloadMock }
    });

    render(<StartupErrorScreen error="Python virtualenv not found" />);

    expect(screen.getByText("StoryForge3 启动失败")).toBeInTheDocument();
    expect(screen.getByText(/Python virtualenv not found/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(reloadMock).toHaveBeenCalledTimes(1);
  });

  it("opens the log directory", async () => {
    render(<StartupErrorScreen error="port already in use" />);

    fireEvent.click(screen.getByRole("button", { name: "查看日志" }));

    await expect.poll(() => openPathMock.mock.calls[0]?.[0]).toContain("storyforge3");
  });
});
