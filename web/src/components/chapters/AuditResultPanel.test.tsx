import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AuditResultPanel } from "./AuditResultPanel";

describe("AuditResultPanel", () => {
  it("summarizes passed, warning, and blocking rule results", () => {
    render(
      <AuditResultPanel
        result={{
          chapter_no: 1,
          passed: false,
          blocking_issues: ["golden_three_hook"],
          warnings: ["markdown_artifacts"],
          info: [],
          rule_results: [
            {
              rule_id: "golden_three_hook",
              passed: false,
              severity: "BLOCKING",
              category: "STRUCTURE",
              message: "前三段缺少有效钩子",
              detail: { score: 0, paragraph_indices: [0], snippet: "今天天气不错，林默走在路上。" }
            },
            {
              rule_id: "markdown_artifacts",
              passed: false,
              severity: "WARNING",
              category: "META",
              message: "存在 Markdown 痕迹",
              detail: {}
            },
            {
              rule_id: "dialogue_punctuation",
              passed: true,
              severity: "INFO",
              category: "STYLE",
              message: "对话标点正常",
              detail: {}
            }
          ]
        }}
      />
    );

    expect(screen.getByText("审计未通过")).toBeInTheDocument();
    expect(screen.getByText("1 passed / 1 warnings / 1 blocking")).toBeInTheDocument();
    expect(screen.getByText("golden_three_hook")).toBeInTheDocument();
    expect(screen.getByText("前三段缺少有效钩子")).toBeInTheDocument();
    expect(screen.getByText("今天天气不错，林默走在路上。")).toBeInTheDocument();
  });

  it("calls onLocateIssue for rules with paragraph locations only", () => {
    const onLocateIssue = vi.fn();
    render(
      <AuditResultPanel
        onLocateIssue={onLocateIssue}
        result={{
          chapter_no: 1,
          passed: false,
          blocking_issues: ["golden_three_hook"],
          warnings: ["hedge_density"],
          info: [],
          rule_results: [
            {
              rule_id: "golden_three_hook",
              passed: false,
              severity: "BLOCKING",
              category: "STRUCTURE",
              message: "前三段缺少有效钩子",
              detail: { paragraph_indices: [0, 1], snippet: "开头太平。" }
            },
            {
              rule_id: "hedge_density",
              passed: false,
              severity: "WARNING",
              category: "STYLE",
              message: "模糊词密度偏高",
              detail: { observed: 12 }
            }
          ]
        }}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: /定位 golden_three_hook/ }));

    expect(onLocateIssue).toHaveBeenCalledWith(expect.objectContaining({ rule_id: "golden_three_hook" }));
    expect(screen.queryByRole("button", { name: /定位 hedge_density/ })).not.toBeInTheDocument();
  });
});
