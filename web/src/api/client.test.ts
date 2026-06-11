import { afterEach, describe, expect, it, vi } from "vitest";
import { api, exportChapterDesktop, resolveApiUrl } from "./client";

const saveMock = vi.fn();
const writeFileMock = vi.fn();

vi.mock("@tauri-apps/plugin-dialog", () => ({
  save: saveMock
}));

vi.mock("@tauri-apps/plugin-fs", () => ({
  writeFile: writeFileMock
}));

describe("api client", () => {
  afterEach(() => {
    Reflect.deleteProperty(window, "__TAURI_INTERNALS__");
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    saveMock.mockReset();
    writeFileMock.mockReset();
  });

  it("unwraps successful API envelopes", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ ok: true, data: { title: "测试小说" }, error: null })))
    );

    await expect(api.get<{ title: string }>("/api/books/one")).resolves.toEqual({ title: "测试小说" });
  });

  it("throws API envelope error messages", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            ok: false,
            data: null,
            error: { code: "BOOK_NOT_FOUND", message: "书籍不存在" }
          }),
          { status: 404 }
        )
      )
    );

    await expect(api.get("/api/books/missing")).rejects.toThrow("书籍不存在");
  });

  it("sends PUT requests with JSON bodies", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ ok: true, data: { saved: true }, error: null })));
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.put<{ saved: boolean }>("/api/books/book-1/world", { setting: "都市异常" })).resolves.toEqual({ saved: true });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/books/book-1/world",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ setting: "都市异常" })
      })
    );
  });

  it("resolves desktop API URLs in Tauri mode", () => {
    Object.defineProperty(window, "__TAURI_INTERNALS__", { configurable: true, value: {} });

    expect(resolveApiUrl("/api/health")).toBe("http://127.0.0.1:8000/api/health");
  });

  it("skips native chapter export outside Tauri mode", async () => {
    await expect(exportChapterDesktop("book-1", 3, "tomato_txt", "第三章")).resolves.toBeNull();

    expect(saveMock).not.toHaveBeenCalled();
    expect(writeFileMock).not.toHaveBeenCalled();
  });

  it("exports a chapter through the native save dialog in Tauri mode", async () => {
    Object.defineProperty(window, "__TAURI_INTERNALS__", { configurable: true, value: {} });
    saveMock.mockResolvedValue("D:/books/第三章.txt");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true, data: { path: "D:/repo/books/book-1/exports/chapter-0003.txt" }, error: null })))
      .mockResolvedValueOnce(new Response("正文内容"));
    vi.stubGlobal("fetch", fetchMock);

    await expect(exportChapterDesktop("book-1", 3, "tomato_txt", "第三章")).resolves.toBe("D:/books/第三章.txt");

    expect(saveMock).toHaveBeenCalledWith({
      defaultPath: "第三章.txt",
      filters: [{ name: "TOMATO_TXT", extensions: ["txt"] }]
    });
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://127.0.0.1:8000/api/books/book-1/chapters/3/export",
      expect.objectContaining({
        body: JSON.stringify({ fmt: "tomato_txt" }),
        method: "POST"
      })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(2, "http://127.0.0.1:8000/api/books/book-1/exports/chapter-0003.txt");
    expect(writeFileMock).toHaveBeenCalledWith("D:/books/第三章.txt", expect.any(Uint8Array));
  });

  it("does not download when native chapter export is canceled", async () => {
    Object.defineProperty(window, "__TAURI_INTERNALS__", { configurable: true, value: {} });
    saveMock.mockResolvedValue(null);
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(exportChapterDesktop("book-1", 3, "tomato_txt", "第三章")).resolves.toBeNull();

    expect(fetchMock).not.toHaveBeenCalled();
    expect(writeFileMock).not.toHaveBeenCalled();
  });
});
