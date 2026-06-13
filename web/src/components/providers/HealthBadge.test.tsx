import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { HealthBadge } from "./HealthBadge";

describe("HealthBadge", () => {
  it("shows 已验证 when verified", () => {
    render(<HealthBadge status="verified" />);
    expect(screen.getByText("已验证")).toBeInTheDocument();
  });

  it("shows 异常 when request_failed", () => {
    render(<HealthBadge status="request_failed" message="timeout" />);
    expect(screen.getByText("异常")).toBeInTheDocument();
  });

  it("shows 未验证 when status is null", () => {
    render(<HealthBadge status={null} />);
    expect(screen.getByText("未验证")).toBeInTheDocument();
  });
});
