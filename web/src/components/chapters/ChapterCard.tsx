import { useState } from "react";
import { AlertTriangle, Check } from "lucide-react";
import type { ChapterResult } from "@/api/chapters";
import type { ChapterConsistency } from "@/api/reconcile";
import { inconsistentReasonLabel } from "@/api/reconcile";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { ChapterPipeline } from "./ChapterPipeline";
import { useChapterStatus } from "@/hooks/useChapters";
import { cn } from "@/lib/utils";

interface ChapterCardProps {
  bookId: string;
  chapter: ChapterConsistency;
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
  truth_committed: "Truth 已提交",
  exported: "已导出",
  needs_review: "需复核",
  consistent: "产物正常",
  inconsistent: "数据不一致"
};

const statusClass: Record<string, string> = {
  planned: "border-indigo-400/30 bg-indigo-400/10 text-indigo-300",
  drafted: "border-amber-300/30 bg-amber-300/10 text-amber-200",
  audited: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
  revised: "border-cyan-400/30 bg-cyan-400/10 text-cyan-300",
  approved: "border-sky-400/30 bg-sky-400/10 text-sky-300",
  truth_committed: "border-violet-300/30 bg-violet-300/10 text-violet-200",
  exported: "border-emerald-300 bg-emerald-400 text-zinc-950",
  needs_revision: "border-red-400/30 bg-red-400/10 text-red-300",
  needs_review: "border-red-400/30 bg-red-400/10 text-red-300",
  consistent: "border-zinc-700 bg-zinc-900/60 text-zinc-400",
  inconsistent: "border-amber-300 bg-amber-300 text-zinc-950"
};

const validityLabels: Record<string, string> = {
  orphan: "孤儿产物：有 Truth/导出但无正文",
  partial: "部分产物"
};

const validityClass: Record<string, string> = {
  orphan: "border-amber-300/30 bg-amber-300/10 text-amber-100",
  partial: "border-sky-300/30 bg-sky-300/10 text-sky-200"
};

const artifactStages = [
  { key: "plan", label: "规划", produced: (chapter: ChapterConsistency) => chapter.has_plan },
  { key: "text", label: "正文", produced: (chapter: ChapterConsistency) => chapter.has_text },
  { key: "truth", label: "Truth", produced: (chapter: ChapterConsistency) => chapter.has_truth },
  { key: "export", label: "导出", produced: (chapter: ChapterConsistency) => chapter.has_export }
] as const;

export function ChapterCard({ bookId, chapter }: ChapterCardProps) {
  const [open, setOpen] = useState(false);
  const chapterNo = chapter.chapter_no;
  const status = chapter.status === "inconsistent" ? "inconsistent" : resolvedStatus(chapter);
  const statusQuery = useChapterStatus(bookId, chapterNo, open);
  const result = statusQuery.data ?? fallbackResult(bookId, chapter);

  return (
    <Card className="overflow-hidden" data-testid={`chapter-card-${chapterNo}`}>
      <button className="flex w-full items-center justify-between gap-4 p-4 text-left hover:bg-zinc-900/50" onClick={() => setOpen(!open)}>
        <div className="min-w-0 space-y-3">
          <p className="text-sm font-medium text-zinc-100">第 {chapterNo} 章</p>
          <div className="flex flex-wrap gap-2">
            {artifactStages.map((stage) => {
              const produced = stage.produced(chapter);
              return (
                <span
                  key={stage.key}
                  data-produced={String(produced)}
                  className={cn(
                    "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs",
                    produced ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-300" : "border-zinc-800 bg-zinc-900/50 text-zinc-600"
                  )}
                >
                  {produced ? <Check className="h-3 w-3" /> : null}
                  {stage.label}
                </span>
              );
            })}
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap justify-end gap-2">
          {validityBadge(chapter.validity)}
          <Badge className={cn(statusClass[status])}>
            {status === "inconsistent" ? <AlertTriangle className="h-3.5 w-3.5" /> : null}
            {statusLabels[status] ?? status}
          </Badge>
        </div>
      </button>
      {open ? (
        <CardContent className="space-y-4">
          {chapter.inconsistent_reasons.length ? (
            <div
              className="rounded-md border border-amber-300/20 bg-amber-300/10 p-3 text-sm text-amber-100"
              data-testid={`chapter-${chapterNo}-inconsistent-reasons`}
            >
              <p className="font-medium text-amber-200">不一致原因</p>
              <ul className="mt-2 space-y-1">
                {chapter.inconsistent_reasons.map((reason) => (
                  <li key={reason}>{inconsistentReasonLabel(reason)}</li>
                ))}
              </ul>
            </div>
          ) : null}
          <ChapterPipeline bookId={bookId} chapterNo={chapterNo} result={result} />
        </CardContent>
      ) : null}
    </Card>
  );
}

function validityBadge(validity: string) {
  const label = validityLabels[validity];
  if (!label) {
    return null;
  }
  return <Badge className={cn(validityClass[validity])}>{label}</Badge>;
}

function resolvedStatus(chapter: ChapterConsistency): string {
  const stateStatus = chapter.state_status?.toLowerCase();
  if (stateStatus) {
    return stateStatus;
  }
  if (chapter.has_export) {
    return "exported";
  }
  if (chapter.has_truth) {
    return "truth_committed";
  }
  if (chapter.has_text) {
    return "drafted";
  }
  if (chapter.has_plan) {
    return "planned";
  }
  return "consistent";
}

function fallbackResult(bookId: string, chapter: ChapterConsistency): ChapterResult {
  const status = chapter.status === "inconsistent" ? "needs_review" : resolvedStatus(chapter);
  return {
    book_id: bookId,
    chapter_no: chapter.chapter_no,
    status,
    title: "未命名",
    text: ""
  };
}
