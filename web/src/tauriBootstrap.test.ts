import { afterEach, describe, expect, it, vi } from "vitest";
import { isTauriEnvironment, waitForApiReady } from "./tauriBootstrap";

describe("tauri bootstrap", () => {
  afterEach(() => {
    Reflect.deleteProperty(window, "__TAURI_INTERNALS__");
    vi.restoreAllMocks();
  });

  it("does not wait for API readiness in web mode", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await waitForApiReady({ retryDelayMs: 1, maxRetries: 2 });

    expect(isTauriEnvironment()).toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("polls the desktop API until health succeeds in Tauri mode", async () => {
    Object.defineProperty(window, "__TAURI_INTERNALS__", { configurable: true, value: {} });
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new Error("not ready"))
      .mockResolvedValueOnce(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await waitForApiReady({ retryDelayMs: 1, maxRetries: 3 });

    expect(isTauriEnvironment()).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock).toHaveBeenCalledWith("http://127.0.0.1:8000/api/health");
  });
});
