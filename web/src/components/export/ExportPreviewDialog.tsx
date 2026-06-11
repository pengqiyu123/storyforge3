import { useEffect, useState } from "react";
import { Copy, Download, Eye } from "lucide-react";
import { toast } from "sonner";
import { chaptersApi, type ExportPreview } from "@/api/chapters";
import { ChapterEditor } from "@/components/editor/ChapterEditor";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select } from "@/components/ui/select";

interface ExportPreviewDialogProps {
  bookId: string;
  chapterNo: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onExport: (format: string) => Promise<void>;
}

const FORMAT_OPTIONS = [
  { value: "tomato_txt", label: "番茄小说" },
  { value: "markdown", label: "Markdown" },
  { value: "qidian_txt", label: "起点中文" }
] as const;

export function ExportPreviewDialog({ bookId, chapterNo, open, onOpenChange, onExport }: ExportPreviewDialogProps) {
  const [format, setFormat] = useState("tomato_txt");
  const [preview, setPreview] = useState<ExportPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) {
      return;
    }
    let cancelled = false;
    async function loadPreview() {
      setLoading(true);
      setError("");
      try {
        const result = await chaptersApi.exportPreview(bookId, chapterNo, format);
        if (!cancelled) {
          setPreview(result);
        }
      } catch (loadError) {
        if (!cancelled) {
          setPreview(null);
          setError(loadError instanceof Error ? loadError.message : "预览加载失败");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    void loadPreview();
    return () => {
      cancelled = true;
    };
  }, [bookId, chapterNo, format, open]);

  async function copyPreview() {
    if (!preview) {
      return;
    }
    await navigator.clipboard.writeText(preview.preview_text);
    toast.success("已复制预览内容");
  }

  async function downloadExport() {
    setExporting(true);
    try {
      await onExport(format);
      toast.success("导出已开始");
    } catch (downloadError) {
      toast.error(downloadError instanceof Error ? downloadError.message : "导出失败");
    } finally {
      setExporting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Eye className="h-4 w-4 text-amber-200" />
            导出预览
          </DialogTitle>
          <DialogDescription>选择格式后预览单章格式化效果，再决定是否导出。</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 p-6 pt-0">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <label className="flex items-center gap-2 text-sm text-zinc-400">
              导出格式
              <Select aria-label="导出格式" value={format} onChange={(event) => setFormat(event.target.value)} className="w-44">
                {FORMAT_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </label>
            <div className="flex flex-wrap items-center gap-3 text-sm text-zinc-500">
              {preview ? <span>字数：{preview.char_count}</span> : null}
              {preview?.format_errors.length ? <span>格式问题：{preview.format_errors.length}</span> : null}
            </div>
          </div>
          {error ? <p className="rounded-md border border-red-400/20 bg-red-400/10 p-3 text-sm text-red-300">{error}</p> : null}
          <ChapterEditor value={loading ? "正在生成预览..." : (preview?.preview_text ?? "")} readOnly className="h-80" />
          {preview?.format_errors.length ? (
            <div className="rounded-md border border-amber-300/20 bg-amber-300/10 p-3 text-sm text-amber-200">
              {preview.format_errors.map((item) => (
                <p key={item}>{item}</p>
              ))}
            </div>
          ) : null}
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" disabled={!preview || loading} onClick={() => void copyPreview()}>
            <Copy className="h-4 w-4" />
            复制全文
          </Button>
          <Button type="button" disabled={!preview || loading || exporting} onClick={() => void downloadExport()}>
            <Download className="h-4 w-4" />
            导出下载
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
