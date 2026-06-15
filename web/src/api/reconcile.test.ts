import { afterEach, describe, expect, it, vi } from "vitest";
import { inconsistentReasonLabel, reconcileApi } from "./reconcile";

describe("reconcileApi", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("loads book reconciliation from the backend envelope", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          ok: true,
          data: {
            book_id: "biedale",
            chapters: [
              {
                chapter_no: 3,
                has_text: false,
                has_plan: false,
                has_truth: true,
                has_export: true,
                has_state: false,
                has_run: false,
                state_status: null,
                status: "inconsistent",
                validity: "orphan",
                inconsistent_reasons: ["export_without_state", "export_without_text", "truth_without_state"]
              }
            ],
            inconsistent_count: 1,
            max_chapter: 3,
            valid_chapter_count: 2,
            highest_contiguous_chapter: 2,
            next_writable_chapter_no: 3,
            has_blocking_inconsistency: true
          },
          error: null
        })
      )
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(reconcileApi.get("biedale")).resolves.toMatchObject({
      book_id: "biedale",
      inconsistent_count: 1,
      max_chapter: 3,
      valid_chapter_count: 2,
      highest_contiguous_chapter: 2,
      next_writable_chapter_no: 3,
      has_blocking_inconsistency: true,
      chapters: [expect.objectContaining({ chapter_no: 3, status: "inconsistent", validity: "orphan" })]
    });
    expect(fetchMock).toHaveBeenCalledWith("/api/books/biedale/reconcile", expect.any(Object));
  });

  it("maps inconsistent reason codes to Chinese labels", () => {
    expect(
      [
        inconsistentReasonLabel("export_without_state"),
        inconsistentReasonLabel("export_without_text"),
        inconsistentReasonLabel("truth_without_state"),
        inconsistentReasonLabel("orphan_state"),
        inconsistentReasonLabel("unknown_reason")
      ]
    ).toMatchInlineSnapshot(`
      [
        "已导出但无状态记录",
        "已导出但无正文文件",
        "有 Truth 但无状态记录",
        "状态记录已完成但缺少正文",
        "unknown_reason",
      ]
    `);
  });
});
