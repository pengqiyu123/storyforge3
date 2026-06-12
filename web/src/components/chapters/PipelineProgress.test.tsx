import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PipelineProgress } from "./PipelineProgress";

describe("PipelineProgress", () => {
  it("renders determinate progress", () => {
    render(<PipelineProgress stage="起草" progress={{ completed: 3, total: 5 }} active />);

    expect(screen.getByText("正在起草...")).toBeInTheDocument();
    expect(screen.getByText("3/5 段")).toBeInTheDocument();
    expect(screen.getByText("正在生成第 3/5 段")).toBeInTheDocument();
    expect(screen.getByTestId("pipeline-progress-bar")).toHaveStyle({ width: "60%" });
  });

  it("renders indeterminate progress", () => {
    render(<PipelineProgress stage="规划" active />);

    expect(screen.getByText("正在规划...")).toBeInTheDocument();
    expect(screen.getByText("正在生成...")).toBeInTheDocument();
    expect(screen.getByTestId("pipeline-progress-bar")).toHaveClass("animate-pulse");
  });

  it("renders error state", () => {
    render(<PipelineProgress stage="起草" active error="Provider 请求超时（300s）" />);

    expect(screen.getByText("起草失败")).toBeInTheDocument();
    expect(screen.getByText("Provider 请求超时（300s）")).toBeInTheDocument();
  });

  it("disappears when not active", () => {
    const { container } = render(<PipelineProgress stage="起草" active={false} progress={{ completed: 1, total: 2 }} />);

    expect(container).toBeEmptyDOMElement();
  });
});
