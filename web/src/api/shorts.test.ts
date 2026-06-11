import { afterEach, describe, expect, it, vi } from "vitest";
import { shortStoriesApi } from "./shorts";

describe("shortStoriesApi", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("creates short stories through the list resource", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          ok: true,
          data: {
            book_id: "story-night-shift",
            title: "夜班",
            genre: "horror",
            status: "empty",
            target_chars: 8000,
            premise: "便利店异常",
            style: "",
            actual_chars: 0,
            created_at: "2026-06-09T00:00:00Z",
            updated_at: "2026-06-09T00:00:00Z"
          },
          error: null
        })
      )
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      shortStoriesApi.create({
        title: "夜班",
        genre: "horror",
        target_chars: 8000,
        premise: "便利店异常",
        style: ""
      })
    ).resolves.toMatchObject({ book_id: "story-night-shift", status: "empty" });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/short-stories",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          title: "夜班",
          genre: "horror",
          target_chars: 8000,
          premise: "便利店异常",
          style: ""
        })
      })
    );
  });

  it("runs the full short story pipeline", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          ok: true,
          data: { book_id: "story-night-shift", status: "exported", text: "短篇正文", error: null },
          error: null
        })
      )
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(shortStoriesApi.runFullPipeline("story-night-shift")).resolves.toMatchObject({ status: "exported" });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/short-stories/story-night-shift/run",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({})
      })
    );
  });
});
