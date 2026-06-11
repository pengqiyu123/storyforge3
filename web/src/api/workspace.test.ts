import { afterEach, describe, expect, it, vi } from "vitest";
import { workspaceApi } from "./workspace";

describe("workspaceApi", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("downloads workspace backup with server filename", async () => {
    const click = vi.fn();
    const remove = vi.fn();
    const anchor = { href: "", download: "", click, remove };
    vi.spyOn(document, "createElement").mockReturnValue(anchor as unknown as HTMLAnchorElement);
    vi.spyOn(document.body, "appendChild").mockImplementation((node) => node);
    const createObjectURL = vi.fn(() => "blob:backup");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(new Blob(["zip"]), {
          headers: { "content-disposition": 'attachment; filename="sf3-backup-20260610.zip"' }
        })
      )
    );

    await workspaceApi.backup();

    expect(fetch).toHaveBeenCalledWith("/api/workspace/backup", { method: "POST" });
    expect(anchor.download).toBe("sf3-backup-20260610.zip");
    expect(click).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:backup");
  });

  it("uploads restore file and unwraps response envelope", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            ok: true,
            data: {
              success: true,
              book_count: 2,
              backup_path: "sf3-backup.zip",
              message: "恢复成功"
            },
            error: null
          })
        )
      )
    );
    const file = new File(["zip"], "backup.zip", { type: "application/zip" });

    const result = await workspaceApi.restore(file);

    expect(fetch).toHaveBeenCalledWith("/api/workspace/restore", expect.objectContaining({ method: "POST" }));
    expect(result.message).toBe("恢复成功");
  });
});
