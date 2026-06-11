import { afterEach, describe, expect, it, vi } from "vitest";
import { chaptersApi } from "./chapters";

describe("chaptersApi", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("updates chapter text through the chapter text resource", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          ok: true,
          data: {
            book_id: "lurenjia",
            chapter_no: 3,
            status: "needs_review",
            title: "第3章",
            text: "林默保存了人工修改。",
            content_hash: "abcd1234",
            actual_chars: 9,
            error: null
          },
          error: null
        })
      )
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      chaptersApi.updateText("lurenjia", 3, {
        text: "林默保存了人工修改。",
        expected_hash: "oldhash1"
      })
    ).resolves.toMatchObject({ status: "needs_review", content_hash: "abcd1234" });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/books/lurenjia/chapters/3/text",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({
          text: "林默保存了人工修改。",
          expected_hash: "oldhash1"
        })
      })
    );
  });

  it("loads export previews from the chapter preview resource", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          ok: true,
          data: {
            chapter_no: 3,
            format: "tomato_txt",
            preview_text: "第3章 第3章\n\n林默站在门口。",
            char_count: 10,
            format_errors: ["word_count_out_of_range"]
          },
          error: null
        })
      )
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(chaptersApi.exportPreview("lurenjia", 3, "tomato_txt")).resolves.toMatchObject({
      format: "tomato_txt",
      format_errors: ["word_count_out_of_range"]
    });

    expect(fetchMock).toHaveBeenCalledWith("/api/books/lurenjia/chapters/3/export-preview?fmt=tomato_txt", expect.any(Object));
  });
});
