import { afterEach, describe, expect, it, vi } from "vitest";

const checkMock = vi.fn();
const getVersionMock = vi.fn();
const relaunchMock = vi.fn();

vi.mock("@tauri-apps/plugin-updater", () => ({
  check: checkMock
}));

vi.mock("@tauri-apps/api/app", () => ({
  getVersion: getVersionMock
}));

vi.mock("@tauri-apps/plugin-process", () => ({
  relaunch: relaunchMock
}));

describe("updater", () => {
  afterEach(() => {
    vi.resetAllMocks();
  });

  it("returns up-to-date when the plugin has no update", async () => {
    const { checkForUpdate } = await import("./updater");
    getVersionMock.mockResolvedValue("0.1.0");
    checkMock.mockResolvedValue(null);

    await expect(checkForUpdate()).resolves.toEqual({ status: "up-to-date" });
  });

  it("maps available updates and accumulates download progress", async () => {
    const { checkForUpdate } = await import("./updater");
    const downloadAndInstall = vi.fn(async (onProgress: (event: unknown) => void) => {
      onProgress({ event: "Started", data: { contentLength: 100 } });
      onProgress({ event: "Progress", data: { chunkLength: 40 } });
      onProgress({ event: "Progress", data: { chunkLength: 60 } });
      onProgress({ event: "Finished" });
    });
    getVersionMock.mockResolvedValue("0.1.0");
    checkMock.mockResolvedValue({
      version: "0.2.0",
      notes: "新增桌面体验",
      date: "2026-06-09",
      downloadAndInstall
    });

    const result = await checkForUpdate();

    expect(result.status).toBe("available");
    if (result.status !== "available") throw new Error("expected update");
    expect(result.info).toEqual({
      currentVersion: "0.1.0",
      availableVersion: "0.2.0",
      notes: "新增桌面体验",
      pubDate: "2026-06-09"
    });

    const progress: Array<{ downloaded: number; total: number }> = [];
    await result.downloadAndInstall((event) => progress.push(event));
    expect(progress).toEqual([
      { downloaded: 0, total: 100 },
      { downloaded: 40, total: 100 },
      { downloaded: 100, total: 100 }
    ]);
  });

  it("relaunches through the Tauri process plugin", async () => {
    const { relaunchApp } = await import("./updater");

    await relaunchApp();

    expect(relaunchMock).toHaveBeenCalledTimes(1);
  });
});
