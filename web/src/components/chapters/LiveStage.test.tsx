import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { RunRecord } from "@/api/runs";
import { LiveStage } from "./LiveStage";

describe("LiveStage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows idle state without run trigger actions", () => {
    render(<LiveStage run={null} />);

    expect(screen.getByText("空闲")).toBeInTheDocument();
    expect(screen.getByText("由 agent 触发生产")).toBeInTheDocument();
    expect(screen.queryByText("运行全流程")).not.toBeInTheDocument();
    expect(screen.queryByText("运行下一阶段")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /取消/ })).not.toBeInTheDocument();
  });

  it("renders stream chunks and stage progress for an active run", () => {
    render(
      <LiveStage
        run={createRunRecord({
          status: "running",
          current_stage: "draft",
          live: {
            stage: "draft",
            progress: { completed: 2, total: 5 },
            streamText: "第一段。\n\n第二段。"
          }
        })}
      />
    );

    expect(screen.getByText("RUNNING")).toBeInTheDocument();
    expect(screen.getByText("起草")).toBeInTheDocument();
    expect(screen.getByText("2/5")).toBeInTheDocument();
    expect(screen.getByText("第一段。")).toBeInTheDocument();
    expect(screen.getByText("第二段。")).toBeInTheDocument();
  });

  it("shows waiting and error/resumable states", () => {
    const { rerender } = render(
      <LiveStage
        run={createRunRecord({
          status: "waiting_for_human",
          current_stage: "approve",
          live: { stage: "approve", waitingMessage: "等待作者批准" }
        })}
      />
    );

    expect(screen.getByText("WAITING_FOR_HUMAN")).toBeInTheDocument();
    expect(screen.getByText("等待作者批准")).toBeInTheDocument();

    rerender(
      <LiveStage
        run={createRunRecord({
          status: "resumable",
          current_stage: "truth",
          error_message: "Truth 提取失败",
          resume_from: "truth",
          live: { stage: "truth", errorMessage: "Truth 提取失败" }
        })}
      />
    );

    expect(screen.getByText("RESUMABLE")).toBeInTheDocument();
    expect(screen.getByText("Truth 提取失败")).toBeInTheDocument();
    expect(screen.getByText("可从 Truth 恢复")).toBeInTheDocument();
  });

  it("shows cancel only for running or waiting runs", async () => {
    const onCancel = vi.fn().mockResolvedValue(undefined);
    const { rerender } = render(<LiveStage run={createRunRecord({ status: "running" })} onCancel={onCancel} />);

    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    await waitFor(() => expect(onCancel).toHaveBeenCalledWith("run-1"));

    rerender(<LiveStage run={createRunRecord({ status: "completed" })} onCancel={onCancel} />);
    expect(screen.queryByRole("button", { name: "取消" })).not.toBeInTheDocument();
  });
});

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
