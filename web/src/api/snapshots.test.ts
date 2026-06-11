import { afterEach, describe, expect, it, vi } from "vitest";
import { snapshotsApi } from "./snapshots";

describe("snapshotsApi", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("loads snapshot list for a book", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          ok: true,
          data: [
            {
              book_id: "lurenjia",
              chapter_no: 5,
              timestamp: "2026-06-10T18:30:00Z",
              file_count: 12,
              path: "20260610T183000000000Z_ch0005.zip"
            }
          ],
          error: null
        })
      )
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(snapshotsApi.list("lurenjia")).resolves.toHaveLength(1);
    expect(fetchMock).toHaveBeenCalledWith("/api/books/lurenjia/snapshots", expect.any(Object));
  });
});
