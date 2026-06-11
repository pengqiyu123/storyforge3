import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ExportPreviewDialog } from "./ExportPreviewDialog";

vi.mock("@/components/editor/ChapterEditor", () => ({
  ChapterEditor: ({ value }: { value: string }) => <textarea aria-label="导出预览正文" readOnly value={value} />
}));

describe("ExportPreviewDialog", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("loads preview, switches format, and copies text", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            ok: true,
            data: {
              chapter_no: 3,
              format: "tomato_txt",
              preview_text: "第3章 第3章\n\n林默站在门口。",
              char_count: 10,
              format_errors: ["word_count_out_of_range"]
            },
            error: null
          })
        )
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            ok: true,
            data: {
              chapter_no: 3,
              format: "markdown",
              preview_text: "## 第3章\n\n林默站在门口。",
              char_count: 10,
              format_errors: []
            },
            error: null
          })
        )
      );
    vi.stubGlobal("fetch", fetchMock);
    const writeText = vi.fn(async () => undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    const onExport = vi.fn(async () => undefined);

    render(<ExportPreviewDialog bookId="lurenjia" chapterNo={3} open onOpenChange={vi.fn()} onExport={onExport} />);

    await waitFor(() => expect(screen.getByText("导出预览")).toBeInTheDocument());
    expect(screen.getByText("word_count_out_of_range")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("导出格式"), { target: { value: "markdown" } });

    await waitFor(() => expect(screen.getByLabelText("导出预览正文")).toHaveValue("## 第3章\n\n林默站在门口。"));

    fireEvent.click(screen.getByRole("button", { name: "复制全文" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("## 第3章\n\n林默站在门口。"));

    fireEvent.click(screen.getByRole("button", { name: "导出下载" }));
    await waitFor(() => expect(onExport).toHaveBeenCalledWith("markdown"));
  });
});
