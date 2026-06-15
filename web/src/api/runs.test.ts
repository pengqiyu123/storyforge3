import { afterEach, describe, expect, it, vi } from "vitest";
import { runsApi } from "./runs";

describe("runsApi", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("loads the current chapter run record", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          ok: true,
          data: createRunRecord({ status: "running", current_stage: "draft" }),
          error: null
        })
      )
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(runsApi.get("biedale", 2)).resolves.toMatchObject({
      run_id: "run-1",
      status: "running",
      current_stage: "draft"
    });
    expect(fetchMock).toHaveBeenCalledWith("/api/books/biedale/chapters/2/run", expect.any(Object));
  });

  it("cancels an active run through the run resource", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          ok: true,
          data: createRunRecord({ status: "cancelled", current_stage: null }),
          error: null
        })
      )
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(runsApi.cancel("biedale", 2, "run-1")).resolves.toMatchObject({
      run_id: "run-1",
      status: "cancelled",
      current_stage: null
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/books/biedale/chapters/2/run/run-1/cancel",
      expect.objectContaining({ method: "POST", body: "{}" })
    );
  });
});

function createRunRecord(overrides: Record<string, unknown> = {}) {
  return {
    run_id: "run-1",
    book_id: "biedale",
    chapter_no: 2,
    mode: "full",
    target_stages: ["plan", "draft", "audit", "revise", "approve", "truth", "export"],
    status: "pending",
    current_stage: null,
    started_at: "2026-06-15T01:00:00Z",
    updated_at: "2026-06-15T01:00:00Z",
    stage_results: {},
    llm_calls: [],
    error_code: null,
    error_message: null,
    resume_from: null,
    ...overrides
  };
}
