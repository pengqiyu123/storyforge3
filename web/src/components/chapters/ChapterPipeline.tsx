import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Check, Eye, Pencil, Play, Save, X } from "lucide-react";
import { exportChapterDesktop, resolveApiUrl } from "@/api/client";
import { chaptersApi, type AuditResult, type ChapterIntent, type ChapterResult, type RevisionDiff, type RuleResult } from "@/api/chapters";
import { ChapterEditor, type HighlightRange } from "@/components/editor/ChapterEditor";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AuditResultPanel } from "@/components/chapters/AuditResultPanel";
import { PipelineProgress } from "@/components/chapters/PipelineProgress";
import { RevisionDiffPanel } from "@/components/chapters/RevisionDiffPanel";
import { ExportPreviewDialog } from "@/components/export/ExportPreviewDialog";
import {
  useChapterApprove,
  useChapterAudit,
  useChapterDraft,
  useChapterExport,
  useChapterPlan,
  useChapterPlanState,
  useChapterRevise,
  useChapterUpdateText,
  useRunFullPipeline
} from "@/hooks/useChapters";
import { usePipelineEvents } from "@/hooks/usePipelineEvents";
import { countChineseChars } from "@/lib/utils";
import { isTauriEnvironment } from "@/tauriBootstrap";

type ActionFn = (chapterNo: number) => Promise<unknown>;

interface ChapterPipelineProps {
  bookId: string;
  chapterNo: number;
  result?: ChapterResult | null;
  onPlan?: ActionFn;
}

const steps = [
  { key: "plan", label: "规划", done: ["planned", "drafted", "audited", "needs_revision", "revised", "approved", "exported"] },
  { key: "draft", label: "起草", done: ["drafted", "audited", "needs_revision", "revised", "approved", "exported"] },
  { key: "audit", label: "审计", done: ["audited", "needs_revision", "revised", "approved", "exported"] },
  { key: "revise", label: "修订", done: ["revised", "approved", "exported"] },
  { key: "approve", label: "批准", done: ["approved", "exported"] },
  { key: "export", label: "导出", done: ["exported"] }
] as const;

export function ChapterPipeline({ bookId, chapterNo, result, onPlan }: ChapterPipelineProps) {
  const plan = useChapterPlan(bookId);
  const persistedPlan = useChapterPlanState(bookId, chapterNo);
  const draft = useChapterDraft(bookId);
  const audit = useChapterAudit(bookId);
  const revise = useChapterRevise(bookId);
  const approve = useChapterApprove(bookId);
  const exportChapter = useChapterExport(bookId);
  const runFull = useRunFullPipeline(bookId);
  const updateText = useChapterUpdateText(bookId);
  const [lastEvent, setLastEvent] = useState("");
  const [lastPlan, setLastPlan] = useState<ChapterIntent | null>(null);
  const [lastAudit, setLastAudit] = useState<AuditResult | null>(null);
  const [lastError, setLastError] = useState("");
  const [pipelineStage, setPipelineStage] = useState<string | null>(null);
  const [chunkProgress, setChunkProgress] = useState<{ completed: number; total: number } | null>(null);
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState("");
  const [lastRevisionDiff, setLastRevisionDiff] = useState<RevisionDiff | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [activeHighlights, setActiveHighlights] = useState<HighlightRange[]>([]);
  const [scrollToOffset, setScrollToOffset] = useState<number | undefined>();
  const currentText = result?.text ?? "";
  const hasText = currentText.trim().length > 0;
  const dirty = editing && editText !== currentText;
  const isSaving = updateText.isPending;
  const isBusy = [plan, draft, audit, revise, approve, exportChapter, runFull, updateText].some((mutation) => mutation.isPending);
  const status = String(result?.status ?? "empty").toLowerCase();

  useEffect(() => {
    if (persistedPlan.data) {
      setLastPlan({
        chapter_no: persistedPlan.data.chapter_no,
        goal: persistedPlan.data.goal,
        outline_node: persistedPlan.data.outline_node,
        arc_context: persistedPlan.data.arc_context ?? "",
        must_keep: persistedPlan.data.must_keep ?? [],
        must_avoid: persistedPlan.data.must_avoid ?? [],
        style_emphasis: persistedPlan.data.style_emphasis ?? []
      });
    }
  }, [persistedPlan.data]);

  usePipelineEvents(bookId, chapterNo, (event) => {
    setLastEvent(event.message || event.stage || "");
    if (event.type === "pipeline:start") {
      setPipelineStage(event.stage || null);
      setChunkProgress(null);
      setLastError("");
    } else if (event.type === "llm:progress" && event.detail) {
      setChunkProgress({
        completed: Number(event.detail.completed) || 0,
        total: Number(event.detail.total) || 0
      });
    } else if (event.type === "pipeline:error") {
      setPipelineStage(event.stage || null);
      setChunkProgress(null);
      setLastError(event.message || "管线运行失败");
    } else if (event.type === "pipeline:complete") {
      setPipelineStage(null);
      setChunkProgress(null);
    }
  });

  async function runAction(label: string, action: () => Promise<unknown>) {
    try {
      clearAuditFocus();
      if (label !== "修订") {
        setLastRevisionDiff(null);
      }
      const value = await action();
      if (isChapterIntent(value)) {
        setLastPlan(value);
      }
      if (isAuditResult(value)) {
        setLastAudit(value);
      }
      if (isChapterResult(value)) {
        setLastRevisionDiff(value.revision_diff ?? null);
      }
      setLastError("");
      if (value === null) {
        return;
      }
      toast.success(`${label}完成`);
    } catch (error) {
      const message = error instanceof Error ? error.message : `${label}失败`;
      const detail = `${label}失败: ${message}`;
      setLastError(detail);
      window.setTimeout(() => setLastError(""), 3000);
      toast.error(message);
    }
  }

  function startEditing() {
    setEditText(currentText);
    clearAuditFocus();
    setLastRevisionDiff(null);
    setEditing(true);
  }

  function discardEdit() {
    setEditText("");
    setEditing(false);
    clearAuditFocus();
    setLastRevisionDiff(null);
  }

  async function saveEdit() {
    if (!dirty || isSaving) {
      return;
    }
    try {
      await updateText.mutateAsync({
        chapterNo,
        text: editText,
        expectedHash: result?.content_hash ?? undefined
      });
      setEditing(false);
      setEditText("");
      setLastError("");
      clearAuditFocus();
      setLastRevisionDiff(null);
      toast.success("保存完成");
    } catch (error) {
      const message = error instanceof Error ? error.message : "保存失败";
      setLastError(`保存失败: ${message}`);
      window.setTimeout(() => setLastError(""), 3000);
      toast.error(message.includes("章节内容已被修改") ? "内容已被修改，请刷新" : message);
    }
  }

  async function runExport() {
    const fmt = "tomato_txt";
    if (isTauriEnvironment()) {
      const savedPath = await exportChapterDesktop(bookId, chapterNo, fmt, result?.title || `第${chapterNo}章`);
      return savedPath;
    }

    return exportChapter.mutateAsync({ chapterNo, args: [fmt] });
  }

  async function exportWithFormat(format: string) {
    if (isTauriEnvironment()) {
      await exportChapterDesktop(bookId, chapterNo, mapPreviewFormat(format), result?.title || `第${chapterNo}章`);
      return;
    }
    const exported = await chaptersApi.exportChapter(bookId, chapterNo, mapPreviewFormat(format));
    const filename = exported.path.split(/[\\/]/).filter(Boolean).at(-1) || exported.path;
    const response = await fetch(resolveApiUrl(`/api/books/${bookId}/exports/${encodeURIComponent(filename)}`));
    if (!response.ok) {
      throw new Error(`导出文件下载失败: ${response.status}`);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  const actions: Record<string, () => Promise<unknown>> = {
    plan: () => (onPlan ? onPlan(chapterNo) : plan.mutateAsync({ chapterNo })),
    draft: () => draft.mutateAsync({ chapterNo }),
    audit: () => audit.mutateAsync({ chapterNo }),
    revise: () => revise.mutateAsync({ chapterNo, args: ["auto"] }),
    approve: () => approve.mutateAsync({ chapterNo }),
    export: runExport
  };

  function clearAuditFocus() {
    setActiveHighlights([]);
    setScrollToOffset(undefined);
  }

  function handleLocateIssue(rule: RuleResult) {
    const indices = Array.isArray(rule.detail?.paragraph_indices)
      ? rule.detail.paragraph_indices.filter((index): index is number => Number.isInteger(index))
      : [];
    if (!indices.length) {
      return;
    }

    const text = editing ? editText : currentText;
    const ranges = paragraphIndicesToRanges(text, indices);
    setActiveHighlights(
      ranges.map((range) => ({
        ...range,
        severity: rule.severity === "BLOCKING" ? "BLOCKING" : "WARNING"
      }))
    );
    setScrollToOffset(ranges[0]?.from);
  }

  useEffect(() => {
    if (!editing) {
      return;
    }
    const handler = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        void saveEdit();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [dirty, editText, editing, isSaving, result?.content_hash]);

  return (
    <Card className="border-zinc-800/80 bg-zinc-950/80">
      <CardHeader>
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
          <CardTitle>第 {chapterNo} 章管线</CardTitle>
          <span className="text-sm text-zinc-500">状态：{status}</span>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="grid grid-cols-3 gap-3 md:grid-cols-6">
          {steps.map((step) => {
            const isDone = (step.done as readonly string[]).includes(status);
            return (
              <Button
                key={step.key}
                variant={isDone ? "default" : "outline"}
                disabled={isBusy}
                onClick={() => runAction(step.label, actions[step.key])}
                className="relative"
              >
                {isDone ? <Check className="h-4 w-4" /> : null}
                {step.label}
              </Button>
            );
          })}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button disabled={isBusy} onClick={() => runAction("全流程", () => runFull.mutateAsync({ chapterNo }))}>
            <Play className="h-4 w-4" />
            运行全流程
          </Button>
          {hasText ? (
            <Button variant="outline" disabled={editing || isBusy} onClick={startEditing}>
              <Pencil className="h-4 w-4" />
              编辑
            </Button>
          ) : null}
          {hasText ? (
            <Button variant="ghost" disabled={isBusy} onClick={() => setPreviewOpen(true)}>
              <Eye className="h-4 w-4" />
              预览
            </Button>
          ) : null}
          {!isBusy && lastEvent ? <span className="text-sm text-zinc-500">{lastEvent}</span> : null}
        </div>
        {isBusy && pipelineStage ? (
          <PipelineProgress stage={pipelineStage} progress={chunkProgress} active={isBusy} error={lastError || null} />
        ) : null}
        {!isBusy && lastError ? <p className="rounded-md border border-red-400/20 bg-red-400/10 p-3 text-sm text-red-300">{lastError}</p> : null}
        {lastPlan ? (
          <div className="rounded-md border border-zinc-800/80 bg-zinc-950/80 p-4 text-sm text-zinc-300" data-testid="chapter-plan-panel">
            <div className="flex items-center justify-between gap-3">
              <span className="font-medium text-zinc-100">本章规划</span>
              <span className="text-xs text-zinc-500">{`第 ${lastPlan.chapter_no} 章`}</span>
            </div>
            <div className="mt-3 space-y-2">
              <p>
                <span className="text-zinc-500">目标：</span>
                {lastPlan.goal}
              </p>
              {lastPlan.outline_node ? (
                <p>
                  <span className="text-zinc-500">卷纲节点：</span>
                  {lastPlan.outline_node}
                </p>
              ) : null}
              {lastPlan.arc_context ? (
                <p>
                  <span className="text-zinc-500">弧线：</span>
                  {lastPlan.arc_context}
                </p>
              ) : null}
              {lastPlan.must_keep.length ? (
                <p>
                  <span className="text-zinc-500">必须保留：</span>
                  {lastPlan.must_keep.join("、")}
                </p>
              ) : null}
              {lastPlan.must_avoid.length ? (
                <p>
                  <span className="text-zinc-500">必须避免：</span>
                  {lastPlan.must_avoid.join("、")}
                </p>
              ) : null}
              {lastPlan.style_emphasis.length ? (
                <p>
                  <span className="text-zinc-500">风格侧重：</span>
                  {lastPlan.style_emphasis.join("、")}
                </p>
              ) : null}
            </div>
          </div>
        ) : null}
        <AuditResultPanel result={lastAudit} onLocateIssue={handleLocateIssue} />
        {lastRevisionDiff ? <RevisionDiffPanel diff={lastRevisionDiff} onClose={() => setLastRevisionDiff(null)} /> : null}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-zinc-300">文本预览</span>
            <span className="text-xs text-zinc-500">{result?.actual_chars ?? countChineseChars(currentText)} 字</span>
          </div>
          <ChapterEditor
            value={editing ? editText : currentText}
            readOnly={!editing}
            onChange={setEditText}
            highlights={activeHighlights}
            scrollToOffset={scrollToOffset}
            placeholder="章节正文会在管线运行后显示。"
            className="h-52"
          />
          {editing ? (
            <div className="flex flex-wrap items-center gap-3 rounded-md border border-zinc-800 bg-zinc-900/60 p-3">
              <Button variant="outline" size="sm" disabled={isSaving} onClick={discardEdit}>
                <X className="h-4 w-4" />
                放弃修改
              </Button>
              <Button size="sm" disabled={!dirty || isSaving} onClick={saveEdit}>
                <Save className="h-4 w-4" />
                保存 (Ctrl+S)
              </Button>
              {dirty ? <span className="text-xs font-medium text-amber-200">未保存的修改</span> : null}
            </div>
          ) : null}
        </div>
      </CardContent>
      <ExportPreviewDialog
        bookId={bookId}
        chapterNo={chapterNo}
        open={previewOpen}
        onOpenChange={setPreviewOpen}
        onExport={exportWithFormat}
      />
    </Card>
  );
}

function isAuditResult(value: unknown): value is AuditResult {
  return Boolean(value && typeof value === "object" && "passed" in value && "blocking_issues" in value && "warnings" in value);
}

function isChapterResult(value: unknown): value is ChapterResult {
  return Boolean(value && typeof value === "object" && "book_id" in value && "chapter_no" in value && "status" in value);
}

function isChapterIntent(value: unknown): value is ChapterIntent {
  return Boolean(value && typeof value === "object" && "goal" in value && "outline_node" in value && "must_keep" in value);
}

export function paragraphIndicesToRanges(text: string, indices: number[]): { from: number; to: number }[] {
  const wanted = new Set(indices);
  const ranges: { from: number; to: number }[] = [];
  const separator = /\n\s*\n|[\r\n]+/g;
  let paragraphIndex = 0;
  let segmentStart = 0;

  function consumeSegment(segmentEnd: number) {
    const raw = text.slice(segmentStart, segmentEnd);
    const leadingTrim = raw.length - raw.trimStart().length;
    const trimmed = raw.trim();
    if (!trimmed) {
      return;
    }
    if (wanted.has(paragraphIndex)) {
      const from = segmentStart + leadingTrim;
      ranges.push({ from, to: from + trimmed.length });
    }
    paragraphIndex += 1;
  }

  for (const match of text.matchAll(separator)) {
    consumeSegment(match.index ?? 0);
    segmentStart = (match.index ?? 0) + match[0].length;
  }
  consumeSegment(text.length);

  return ranges;
}

function mapPreviewFormat(format: string) {
  if (format === "markdown") {
    return "md";
  }
  return format;
}
