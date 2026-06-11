import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RevisionDiffPanel } from "./RevisionDiffPanel";

describe("RevisionDiffPanel", () => {
  it("renders summary and all diff block kinds", () => {
    render(
      <RevisionDiffPanel
        diff={{
          unit: "paragraph",
          summary: {
            changed_blocks: 1,
            added_blocks: 1,
            removed_blocks: 1,
            before_chars: 20,
            after_chars: 24
          },
          blocks: [
            { kind: "replace", before_text: "修订前段落。", after_text: "修订后段落。" },
            { kind: "insert", before_text: "", after_text: "新增段落。" },
            { kind: "delete", before_text: "删除段落。", after_text: "" }
          ]
        }}
      />
    );

    expect(screen.getByText("修订变更")).toBeInTheDocument();
    expect(screen.getByText("改动 1 段")).toBeInTheDocument();
    expect(screen.getByText("新增 1 段")).toBeInTheDocument();
    expect(screen.getByText("删除 1 段")).toBeInTheDocument();
    expect(screen.getByText("20 → 24 字")).toBeInTheDocument();
    expect(screen.getAllByText("修订前").length).toBe(3);
    expect(screen.getAllByText("修订后").length).toBe(3);
    expect(screen.getByText("修订前段落。")).toBeInTheDocument();
    expect(screen.getByText("新增段落。")).toBeInTheDocument();
    expect(screen.getByText("删除段落。")).toBeInTheDocument();
    expect(screen.getByText("（删除）")).toBeInTheDocument();
  });

  it("calls onClose from the close button", () => {
    const onClose = vi.fn();
    render(
      <RevisionDiffPanel
        diff={{
          unit: "paragraph",
          summary: {
            changed_blocks: 1,
            added_blocks: 0,
            removed_blocks: 0,
            before_chars: 10,
            after_chars: 12
          },
          blocks: [{ kind: "replace", before_text: "旧稿。", after_text: "新稿。" }]
        }}
        onClose={onClose}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "关闭修订变更" }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
