import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { RunRecord } from "@/api/runs";
import { RunTrack } from "./RunTrack";

describe("RunTrack", () => {
  it("renders the seven agent stages in order", () => {
    render(<RunTrack chapterStatus="empty" run={null} />);

    expect(screen.getAllByTestId("run-track-stage").map((node) => node.textContent)).toEqual([
      expect.stringContaining("规划"),
      expect.stringContaining("起草"),
      expect.stringContaining("审计"),
      expect.stringContaining("修订"),
      expect.stringContaining("批准"),
      expect.stringContaining("Truth"),
      expect.stringContaining("导出")
    ]);
  });

  it("marks completed, skipped, running, and locked stages from the run record", () => {
    render(
      <RunTrack
        chapterStatus="drafted"
        run={createRunRecord({
          status: "running",
          current_stage: "audit",
          stage_results: {
            plan: stage("plan", "completed"),
            draft: stage("draft", "completed"),
            revise: stage("revise", "skipped")
          }
        })}
      />
    );

    expect(stageNode("规划")).toHaveAttribute("data-state", "completed");
    expect(stageNode("起草")).toHaveAttribute("data-state", "completed");
    expect(stageNode("审计")).toHaveAttribute("data-state", "running");
    expect(stageNode("修订")).toHaveAttribute("data-state", "skipped");
    expect(stageNode("Truth")).toHaveAttribute("data-state", "locked");
  });

  it("uses chapter status for idle static completion", () => {
    render(<RunTrack chapterStatus="truth_committed" run={null} />);

    expect(stageNode("规划")).toHaveAttribute("data-state", "completed");
    expect(stageNode("起草")).toHaveAttribute("data-state", "completed");
    expect(stageNode("批准")).toHaveAttribute("data-state", "completed");
    expect(stageNode("Truth")).toHaveAttribute("data-state", "completed");
    expect(stageNode("导出")).toHaveAttribute("data-state", "locked");
  });
});

function stageNode(label: string) {
  return screen.getAllByTestId("run-track-stage").find((node) => within(node).queryByText(label)) ?? screen.getByText(label);
}

function stage(stageName: string, status: string) {
  return {
    stage: stageName,
    status,
    started_at: "2026-06-15T01:00:00Z",
    finished_at: status === "running" ? null : "2026-06-15T01:01:00Z",
    duration_ms: 1000,
    error_code: null,
    error_message: null,
    summary: null
  };
}

function createRunRecord(overrides: Partial<RunRecord> = {}): RunRecord {
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
