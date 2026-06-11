import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { CreateShortDialog } from "./CreateShortDialog";

describe("CreateShortDialog", () => {
  it("submits short story form data and navigates to the detail page", async () => {
    const onCreate = vi.fn().mockResolvedValue({ book_id: "story-night-shift" });

    render(
      <MemoryRouter initialEntries={["/shorts"]}>
        <Routes>
          <Route
            path="/shorts"
            element={
              <>
                <CreateShortDialog onCreate={onCreate} />
                <LocationProbe />
              </>
            }
          />
          <Route path="/shorts/:id" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    );

    fireEvent.click(screen.getByRole("button", { name: "创建短篇" }));
    fireEvent.change(screen.getByLabelText("标题"), { target: { value: "夜班" } });
    fireEvent.change(screen.getByLabelText("类型"), { target: { value: "horror" } });
    fireEvent.change(screen.getByLabelText("目标字数"), { target: { value: "8000" } });
    fireEvent.change(screen.getByLabelText("核心设定"), { target: { value: "便利店异常" } });
    fireEvent.change(screen.getByLabelText("风格"), { target: { value: "冷峻悬疑" } });
    fireEvent.click(screen.getByRole("button", { name: "创建" }));

    await waitFor(() =>
      expect(onCreate).toHaveBeenCalledWith({
        title: "夜班",
        genre: "horror",
        target_chars: 8000,
        premise: "便利店异常",
        style: "冷峻悬疑"
      })
    );
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/shorts/story-night-shift"));
  });
});

function LocationProbe() {
  const location = useLocation();
  return <span data-testid="location">{location.pathname}</span>;
}
