import { useEffect, useState } from "react";
import { Check, Pencil, Save, X } from "lucide-react";
import type { ChapterIntent, ChapterResult } from "@/api/chapters";
import { AuditResultPanel } from "@/components/chapters/AuditResultPanel";
import { RevisionDiffPanel } from "@/components/chapters/RevisionDiffPanel";
import { ChapterEditor } from "@/components/editor/ChapterEditor";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { LiveStage } from "@/components/chapters/LiveStage";
import { PipelineProgress } from "@/components/chapters/PipelineProgress";
import { RunTrack } from "@/components/chapters/RunTrack";
import { ExportPreviewDialog } from "@/components/export/ExportPreviewDialog";
import { useChapterPlanState, useChapterUpdateText } from "@/hooks/useChapters";
import { usePipelineEvents } from "@/hooks/usePipelineEvents";
import { useCancelRun, useRunRecord } from "@/hooks/useRunRecord";
import { useRunEvents } from "@/hooks/useRunEvents";
import { countChineseChars } from "@/lib/utils";

/**
 * ChapterPipeline — READ-ONLY Run Viewer (agent-mode only).
 *
 * The six stages are VIEW TABS: clicking switches to that stage's result;
 * the checkmark only indicates "this stage has produced output". They do NOT
 * trigger runs. Running (plan/draft/audit/revise/truth/export) is driven by the
 * agent / external API; this component only watches (SSE) and displays results.
 * Manual text editing remains (the author refines prose by hand).
 *
 * See `CLAUDE.md` "Product Direction — agent-mode ONLY" and
 * `docs/architecture-run-state-and-viewer.md`. Full per-stage result persistence
 * (so every tab is always loadable) is P1.
 */

interface ChapterPipelineProps {
  bookId: string;
  chapterNo: number;
  result?: ChapterResult | null;
}

const stages = [
  { key: "plan", label: "规划", done: ["planned", "drafted", "audited", "needs_revision", "revised", "approved", "truth_committed", "exported"] },
  { key: "draft", label: "起草", done: ["drafted", "audited", "needs_revision", "revised", "approved", "truth_committed", "exported"] },
  { key: "audit", label: "审计", done: ["audited", "needs_revision", "revised", "approved", "truth_committed", "exported"] },
  { key: "revise", label: "修订", done: ["revised", "approved", "truth_committed", "exported"] },
  { key: "approve", label: "批准", done: ["approved", "truth_committed", "exported"] },
  { key: "export", label: "导出", done: ["exported"] }
] as const;

const statusLabels: Record<string, string> = {
  empty: "未开始",
  planned: "已规划",
  drafted: "已起草",
  audited: "已审计",
  needs_revision: "需修订",
  revised: "已修订",
  approved: "已批准",
  truth_committed: "Truth 已提交",
  exported: "已导出",
  needs_review: "需复核"
};

export function ChapterPipeline({ bookId, chapterNo, result }: ChapterPipelineProps) {
  const persistedPlan = useChapterPlanState(bookId, chapterNo);
  const runRecord = useRunRecord(bookId, chapterNo);
  const cancelRun = useCancelRun(bookId, chapterNo);
  const updateText = useChapterUpdateText(bookId);
  const [activeStage, setActiveStage] = useState<string>("draft");
  const [lastEvent, setLastEvent] = useState("");
  const [lastPlan, setLastPlan] = useState<ChapterIntent | null>(null);
  const [lastError, setLastError] = useState("");
  const [pipelineStage, setPipelineStage] = useState<string | null>(null);
  const [chunkProgress, setChunkProgress] = useState<{ completed: number; total: number } | null>(null);
  const [streamingText, setStreamingText] = useState("");
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState("");
  const [previewOpen, setPreviewOpen] = useState(false);
  const currentText = result?.text ?? "";
  const hasText = currentText.trim().length > 0;
  const dirty = editing && editText !== currentText;
  const isSaving = updateText.isPending;
  const status = String(result?.status ?? "empty").toLowerCase();
  const running = Boolean(pipelineStage);

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
      setStreamingText("");
      if (event.stage) {
        setActiveStage(event.stage);
      }
    } else if (event.type === "llm:progress" && event.detail) {
      setChunkProgress({
        completed: Number(event.detail.completed) || 0,
        total: Number(event.detail.total) || 0
      });
    } else if (event.type === "llm:chunk" && event.detail && typeof event.detail.text === "string") {
      setStreamingText((prev) => (prev ? `${prev}\n\n${event.detail?.text}` : String(event.detail?.text)));
    } else if (event.type === "pipeline:error") {
      setPipelineStage(event.stage || null);
      setChunkProgress(null);
      setLastError(event.message || "管线运行失败");
      setStreamingText("");
    } else if (event.type === "pipeline:complete") {
      setPipelineStage(null);
      setChunkProgress(null);
      setStreamingText("");
    }
  });

  useRunEvents(bookId, chapterNo);

  function startEditing() {
    setEditText(currentText);
    setEditing(true);
  }

  function discardEdit() {
    setEditText("");
    setEditing(false);
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
    } catch (error) {
      const message = error instanceof Error ? error.message : "保存失败";
      setLastError(`保存失败: ${message}`);
      window.setTimeout(() => setLastError(""), 3000);
    }
  }

  useEffect(() => {
    if (!editing) {
      return undefined;
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
          <CardTitle className="text-base">第 {chapterNo} 章</CardTitle>
          <div className="flex items-center gap-3">
            <Badge variant="muted">{statusLabels[status] ?? status}</Badge>
            <span className="text-xs text-zinc-500">{result?.actual_chars ?? countChineseChars(currentText)} 字</span>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        <RunTrack chapterStatus={status} run={runRecord.data ?? null} />
        <LiveStage
          run={runRecord.data ?? null}
          isCancelling={cancelRun.isPending}
          onCancel={(runId) => cancelRun.mutateAsync(runId)}
        />

        {/* Stage view tabs — click to VIEW a stage; checkmark = produced output. Never a run trigger. */}
        <div className="grid grid-cols-3 gap-3 md:grid-cols-6" role="tablist" aria-label="章节阶段">
          {stages.map((stage) => {
            const isDone = (stage.done as readonly string[]).includes(status);
            const isActive = activeStage === stage.key;
            return (
              <Button
                key={stage.key}
                role="tab"
                aria-selected={isActive}
                variant={isActive ? "default" : "outline"}
                onClick={() => setActiveStage(stage.key)}
                className="relative"
              >
                {isDone ? <Check className="h-4 w-4" /> : null}
                {stage.label}
              </Button>
            );
          })}
        </div>

        {/* Live run indicator — the viewer shows agent-driven progress, no button needed. */}
        {pipelineStage ? (
          <PipelineProgress stage={pipelineStage} progress={chunkProgress} active error={lastError || null} />
        ) : null}
        {!pipelineStage && lastError ? (
          <p className="rounded-md border border-red-400/20 bg-red-400/10 p-3 text-sm text-red-300">{lastError}</p>
        ) : null}
        {!pipelineStage && lastEvent ? <p className="text-sm text-zinc-500">{lastEvent}</p> : null}

        {/* Active stage view */}
        {activeStage === "plan" ? <PlanView plan={lastPlan} /> : null}

        {activeStage === "draft" ? (
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm font-medium text-zinc-300">
                {streamingText ? "正在生成（流式）…" : hasText ? "正文" : "尚未起草"}
              </span>
              {hasText && !editing ? (
                <Button variant="outline" size="sm" disabled={running} onClick={startEditing}>
                  <Pencil className="h-4 w-4" />
                  编辑
                </Button>
              ) : null}
            </div>
            <ChapterEditor
              value={editing ? editText : streamingText || currentText}
              readOnly={!editing}
              onChange={setEditText}
              placeholder={running ? "正在生成……" : "章节正文会在 agent 起草后显示。"}
              className="h-64"
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
        ) : null}

        {activeStage === "audit" ? (
          result?.audit_result ? (
            <AuditResultPanel result={result.audit_result} />
          ) : (
            <PlaceholderView label="审计结果" status={status} readyAt={["audited", "needs_revision", "revised", "approved", "truth_committed", "exported"]} />
          )
        ) : null}
        {activeStage === "revise" ? (
          result?.revision_diff ? (
            <RevisionDiffPanel diff={result.revision_diff} />
          ) : (
            <PlaceholderView label="修订 diff" status={status} readyAt={["revised", "approved", "truth_committed", "exported"]} />
          )
        ) : null}
        {activeStage === "approve" ? (
          ["approved", "truth_committed", "exported"].includes(status) ? (
            <div className="rounded-md border border-zinc-800/80 bg-zinc-950/80 p-4 text-sm text-zinc-300">
              <p className="font-medium text-zinc-100">批准记录</p>
              <p className="mt-1 text-zinc-500">本章已批准。Truth 提取和导出已自动执行。</p>
            </div>
          ) : (
            <PlaceholderView label="批准记录" status={status} readyAt={["approved", "truth_committed", "exported"]} />
          )
        ) : null}

        {activeStage === "export" ? (
          <div className="space-y-3">
            <PlaceholderView label="导出记录" status={status} readyAt={["exported"]} />
            <Button variant="outline" size="sm" disabled={!hasText} onClick={() => setPreviewOpen(true)}>
              预览导出格式
            </Button>
          </div>
        ) : null}
      </CardContent>

      <ExportPreviewDialog
        bookId={bookId}
        chapterNo={chapterNo}
        open={previewOpen}
        onOpenChange={setPreviewOpen}
        onExport={() => Promise.resolve()}
      />
    </Card>
  );
}

function PlanView({ plan }: { plan: ChapterIntent | null }) {
  if (!plan) {
    return <PlaceholderView label="本章规划" status="empty" readyAt={["planned", "drafted", "audited", "needs_revision", "revised", "approved", "exported"]} />;
  }
  return (
    <div className="rounded-md border border-zinc-800/80 bg-zinc-950/80 p-4 text-sm text-zinc-300" data-testid="chapter-plan-panel">
      <div className="flex items-center justify-between gap-3">
        <span className="font-medium text-zinc-100">本章规划</span>
        <span className="text-xs text-zinc-500">{`第 ${plan.chapter_no} 章`}</span>
      </div>
      <div className="mt-3 space-y-2">
        <p>
          <span className="text-zinc-500">目标：</span>
          {plan.goal}
        </p>
        {plan.outline_node ? (
          <p>
            <span className="text-zinc-500">卷纲节点：</span>
            {plan.outline_node}
          </p>
        ) : null}
        {plan.arc_context ? (
          <p>
            <span className="text-zinc-500">弧线：</span>
            {plan.arc_context}
          </p>
        ) : null}
        {plan.must_keep.length ? (
          <p>
            <span className="text-zinc-500">必须保留：</span>
            {plan.must_keep.join("、")}
          </p>
        ) : null}
        {plan.must_avoid.length ? (
          <p>
            <span className="text-zinc-500">必须避免：</span>
            {plan.must_avoid.join("、")}
          </p>
        ) : null}
        {plan.style_emphasis.length ? (
          <p>
            <span className="text-zinc-500">风格侧重：</span>
            {plan.style_emphasis.join("、")}
          </p>
        ) : null}
      </div>
    </div>
  );
}

function PlaceholderView({ label, status, readyAt }: { label: string; status: string; readyAt: readonly string[] }) {
  const ready = readyAt.includes(status);
  return (
    <div className="rounded-md border border-zinc-800 bg-zinc-950/50 p-4 text-sm text-zinc-500">
      <p className="font-medium text-zinc-300">{label}</p>
      <p className="mt-1">
        {ready
          ? "该阶段已产出，详细结果视图将在 P1（每阶段产物持久化 + Run Viewer）落地后在此展示。"
          : "该阶段尚未由 agent 运行。运行由 agent / API 触发，UI 仅查看。"}
      </p>
    </div>
  );
}

// Kept for backward compatibility (unit-tested). Paragraph-to-range mapping used by
// the audit "locate issue" feature, which returns with P1 audit-result persistence.
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
