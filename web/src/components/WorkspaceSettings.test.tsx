import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { WorkspaceSettings } from "./WorkspaceSettings";

const { workspaceApiMock } = vi.hoisted(() => ({
  workspaceApiMock: {
    validate: vi.fn(),
    backup: vi.fn(),
    restore: vi.fn()
  }
}));

vi.mock("@/api/workspace", () => ({
  workspaceApi: workspaceApiMock
}));

describe("WorkspaceSettings", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    workspaceApiMock.validate.mockReset();
    workspaceApiMock.backup.mockReset();
    workspaceApiMock.restore.mockReset();
  });

  it("validates workspace, creates backup, and restores after confirmation", async () => {
    workspaceApiMock.validate
      .mockResolvedValueOnce({
        valid: true,
        books_dir: "D:/python/Novel/storyforge3/books",
        book_count: 2,
        issues: []
      })
      .mockResolvedValueOnce({
        valid: true,
        books_dir: "D:/python/Novel/storyforge3/books",
        book_count: 3,
        issues: []
      });
    workspaceApiMock.backup.mockResolvedValue(undefined);
    workspaceApiMock.restore.mockResolvedValue({
      success: true,
      book_count: 3,
      backup_path: "D:/python/Novel/storyforge3/sf3-backup.zip",
      message: "恢复成功，共 3 本书。"
    });

    render(<WorkspaceSettings />);

    fireEvent.click(screen.getByRole("button", { name: "验证" }));

    await waitFor(() => expect(screen.getByText("D:/python/Novel/storyforge3/books")).toBeInTheDocument());
    expect(screen.getByText("2 本")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "创建备份" }));
    await waitFor(() => expect(workspaceApiMock.backup).toHaveBeenCalledTimes(1));

    const file = new File(["zip-bytes"], "backup.zip", { type: "application/zip" });
    fireEvent.change(screen.getByLabelText("选择工作区备份文件"), { target: { files: [file] } });

    expect(screen.getByText("确认恢复工作区")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "确认恢复" }));

    await waitFor(() => expect(workspaceApiMock.restore).toHaveBeenCalledWith(file));
    expect(screen.getByText("恢复成功，共 3 本书。")).toBeInTheDocument();
    expect(screen.getByText("安全备份：D:/python/Novel/storyforge3/sf3-backup.zip")).toBeInTheDocument();
    expect(workspaceApiMock.validate).toHaveBeenCalledTimes(2);
  });
});
