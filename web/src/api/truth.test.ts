import { afterEach, describe, expect, it, vi } from "vitest";
import { truthApi } from "./truth";

describe("truthApi", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("loads truth history from the history endpoint", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          ok: true,
          data: [
            {
              chapter_no: 1,
              source: "runtime_native",
              fact_assertions: ["第1章事实。"],
              character_updates: [],
              relationship_updates: [],
              hook_updates: [],
              irreversible_facts: [],
              notes: []
            }
          ],
          error: null
        })
      )
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(truthApi.history("lurenjia")).resolves.toHaveLength(1);

    expect(fetchMock).toHaveBeenCalledWith("/api/books/lurenjia/truth/history", expect.any(Object));
  });
});
