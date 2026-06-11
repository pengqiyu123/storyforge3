import { act, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useUpdate } from "./UpdateContext";

const { checkForUpdateMock, relaunchAppMock } = vi.hoisted(() => ({
  checkForUpdateMock: vi.fn(),
  relaunchAppMock: vi.fn()
}));

vi.mock("@/lib/updater", () => ({
  checkForUpdate: checkForUpdateMock,
  relaunchApp: relaunchAppMock
}));

function Consumer() {
  const update = useUpdate();
  return (
    <div>
      <span>{update.hasUpdate ? update.updateInfo?.availableVersion : "none"}</span>
      <span>{update.isDismissed ? "dismissed" : "active"}</span>
      <span>{update.isUpdating ? "updating" : "idle"}</span>
      <button onClick={() => void update.checkUpdate()}>检查</button>
      <button onClick={() => update.dismissUpdate()}>忽略</button>
      <button onClick={() => void update.startUpdate()}>更新</button>
    </div>
  );
}

describe("UpdateContext", () => {
  afterEach(() => {
    localStorage.clear();
    vi.useRealTimers();
    vi.resetAllMocks();
  });

  it("checks updates and persists dismissed versions", async () => {
    const { UpdateProvider } = await import("./UpdateContext");
    checkForUpdateMock.mockResolvedValue({
      status: "available",
      info: { currentVersion: "0.1.0", availableVersion: "0.2.0" },
      downloadAndInstall: vi.fn()
    });

    render(
      <UpdateProvider autoCheck={false}>
        <Consumer />
      </UpdateProvider>
    );

    await act(async () => {
      screen.getByRole("button", { name: "检查" }).click();
    });

    await waitFor(() => expect(screen.getByText("0.2.0")).toBeInTheDocument());
    await act(async () => {
      screen.getByRole("button", { name: "忽略" }).click();
    });

    await waitFor(() => expect(screen.getByText("dismissed")).toBeInTheDocument());
    expect(localStorage.getItem("storyforge3:update:dismissedVersion")).toBe("0.2.0");
  });

  it("downloads, installs, and relaunches from the update handle", async () => {
    const { UpdateProvider } = await import("./UpdateContext");
    const downloadAndInstall = vi.fn();
    checkForUpdateMock.mockResolvedValue({
      status: "available",
      info: { currentVersion: "0.1.0", availableVersion: "0.2.0" },
      downloadAndInstall
    });

    render(
      <UpdateProvider autoCheck={false}>
        <Consumer />
      </UpdateProvider>
    );

    await act(async () => {
      screen.getByRole("button", { name: "检查" }).click();
    });
    await act(async () => {
      screen.getByRole("button", { name: "更新" }).click();
    });

    expect(downloadAndInstall).toHaveBeenCalledTimes(1);
    expect(relaunchAppMock).toHaveBeenCalledTimes(1);
  });

  it("auto-checks after startup when enabled", async () => {
    vi.useFakeTimers();
    const { UpdateProvider } = await import("./UpdateContext");
    checkForUpdateMock.mockResolvedValue({ status: "up-to-date" });
    const wrapper = ({ children }: { children: ReactNode }) => <UpdateProvider>{children}</UpdateProvider>;

    render(<Consumer />, { wrapper });
    await act(async () => {
      vi.advanceTimersByTime(2000);
    });

    expect(checkForUpdateMock).toHaveBeenCalledTimes(1);
  });
});
