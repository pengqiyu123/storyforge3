import { useState } from "react";
import type { ChapterResult } from "@/api/chapters";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { useChapterStatus } from "@/hooks/useChapters";
import { ChapterPipeline } from "./ChapterPipeline";
import { cn } from "@/lib/utils";

interface ChapterCardProps {
  bookId: string;
  chapterNo: number;
}

const statusLabels: Record<string, string> = {
  empty: "未开始",
  planned: "已规划",
  drafted: "已起草",
  settled: "已沉淀",
  audited: "已审计",
  needs_revision: "需修订",
  revised: "已修订",
  approved: "已批准",
  exported: "已导出",
  needs_review: "需复核"
};

const statusClass: Record<string, string> = {
  planned: "border-indigo-400/30 bg-indigo-400/10 text-indigo-300",
  drafted: "border-amber-300/30 bg-amber-300/10 text-amber-200",
  audited: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
  revised: "border-cyan-400/30 bg-cyan-400/10 text-cyan-300",
  approved: "border-sky-400/30 bg-sky-400/10 text-sky-300",
  exported: "border-emerald-300 bg-emerald-400 text-zinc-950",
  needs_revision: "border-red-400/30 bg-red-400/10 text-red-300",
  needs_review: "border-red-400/30 bg-red-400/10 text-red-300"
};

export function ChapterCard({ bookId, chapterNo }: ChapterCardProps) {
  const [open, setOpen] = useState(false);
  const query = useChapterStatus(bookId, chapterNo);
  const result = query.data ?? fallbackResult(bookId, chapterNo);
  const status = String(result.status ?? "empty").toLowerCase();

  return (
    <Card className="overflow-hidden">
      <button className="flex w-full items-center justify-between gap-4 p-4 text-left hover:bg-zinc-900/50" onClick={() => setOpen(!open)}>
        <div>
          <p className="text-sm font-medium text-zinc-100">第 {chapterNo} 章</p>
          <p className="mt-1 text-xs text-zinc-500">{result.title || "未命名"}</p>
        </div>
        <Badge className={cn("shrink-0", statusClass[status])}>{statusLabels[status] ?? status}</Badge>
      </button>
      {open ? (
        <CardContent>
          <ChapterPipeline bookId={bookId} chapterNo={chapterNo} result={result} />
        </CardContent>
      ) : null}
    </Card>
  );
}

function fallbackResult(bookId: string, chapterNo: number): ChapterResult {
  return {
    book_id: bookId,
    chapter_no: chapterNo,
    status: "empty",
    title: "未命名",
    text: ""
  };
}
