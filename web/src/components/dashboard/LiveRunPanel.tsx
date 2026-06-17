import { useEffect, useRef, useState } from "react";
import { Check, CircleDot, Loader2, XCircle, Circle, Radio } from "lucide-react";
import type { LiveRunState, StageStatus } from "@/hooks/useGlobalRunEvents";
import { cn } from "@/lib/utils";

/**
 * LiveRunPanel — dashboard's real-time agent activity panel.
 *
 * Shows what the agent is doing right now: which chapter, which stage,
 * elapsed time, and a streaming text area for LLM output.
 * Subscribes to ALL SSE events globally (not per-chapter).
 */

const STAGE_LABELS: Record<string, string> = {
  plan: "规划",
  draft: "起草",
  audit: "审计",
  revise: "修订",
  approve: "批准",
  truth: "Truth",
  export: "导出",
  normalize: "规范化",
};

const STAGE_ORDER = ["plan", "draft", "normalize", "audit", "revise", "approve", "truth", "export"];

interface LiveRunPanelProps {
  runs: LiveRunState[];
}

export function LiveRunPanel({ runs }: LiveRunPanelProps) {
  if (runs.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3">
      {runs.map((run) => (
        <RunCard key={`${run.bookId}:${run.chapterNo}`} run={run} />
      ))}
    </div>
  );
}

function RunCard({ run }: { run: LiveRunState }) {
  const isRunning = run.currentStage !== null;
  const hasError = Boolean(run.errorMessage);
  const stageLabel = run.currentStage ? (STAGE_LABELS[run.currentStage] ?? run.currentStage) : "完成";

  return (
    <div
      className={cn(
        "rounded-lg border bg-zinc-950/80 p-5 shadow-xl shadow-black/20 transition-colors",
        hasError ? "border-red-500/40" : isRunning ? "border-amber-300/40" : "border-emerald-500/30"
      )}
    >
      {/* Header: book + chapter + status badge */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span
            className={cn(
              "flex h-8 w-8 items-center justify-center rounded-full",
              hasError ? "bg-red-500/15 text-red-300" : isRunning ? "bg-amber-300/15 text-amber-200" : "bg-emerald-500/15 text-emerald-300"
            )}
          >
            {hasError ? <XCircle className="h-4 w-4" /> : isRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
          </span>
          <div>
            <p className="text-sm font-medium text-zinc-100">
              第 {run.chapterNo} 章
              <span className="ml-2 text-xs text-zinc-500">{run.bookTitle}</span>
            </p>
            <p className="text-xs text-zinc-500">
              {hasError ? run.errorMessage : isRunning ? `正在${stageLabel}` : `${stageLabel}完成`}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isRunning ? (
            <span className="flex items-center gap-1.5 rounded-full bg-amber-300/10 px-3 py-1 text-xs text-amber-200">
              <Radio className="h-3 w-3 animate-pulse" />
              LIVE
            </span>
          ) : null}
          <ElapsedTimer startedAt={run.startedAt} running={isRunning} />
        </div>
      </div>

      {/* Stage track */}
      <div className="mt-4 flex flex-wrap gap-2">
        {STAGE_ORDER.map((stageKey) => {
          const status = run.stageStatuses[stageKey] ?? "pending";
          const label = STAGE_LABELS[stageKey] ?? stageKey;
          return <StageChip key={stageKey} label={label} status={status} />;
        })}
      </div>

      {/* Streaming text area */}
      {run.streamText ? (
        <div className="mt-4">
          <p className="mb-1.5 text-xs text-zinc-500">
            {run.currentStage === "draft" ? "正文输出" : "LLM 输出"}
          </p>
          <div className="max-h-48 overflow-y-auto rounded-md border border-zinc-800 bg-zinc-900/50 p-3">
            <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-relaxed text-zinc-300">
              {run.streamText}
              {isRunning && run.currentStage === "draft" ? (
                <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-amber-300 align-middle" />
              ) : null}
            </pre>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function StageChip({ label, status }: { label: string; status: StageStatus }) {
  const Icon = statusIcon(status);
  return (
    <span
      className={cn(
        "flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
        status === "completed" && "bg-emerald-500/10 text-emerald-300",
        status === "running" && "bg-amber-300/15 text-amber-200 ring-1 ring-amber-300/30",
        status === "failed" && "bg-red-500/10 text-red-300",
        status === "pending" && "bg-zinc-800/50 text-zinc-500"
      )}
    >
      <Icon className={cn("h-3 w-3", status === "running" && "animate-spin")} />
      {label}
    </span>
  );
}

function statusIcon(status: StageStatus) {
  if (status === "completed") return Check;
  if (status === "running") return Loader2;
  if (status === "failed") return XCircle;
  return Circle;
}

function ElapsedTimer({ startedAt, running }: { startedAt: number; running: boolean }) {
  const [elapsed, setElapsed] = useState(() => formatElapsed(startedAt));

  useEffect(() => {
    if (!running) {
      setElapsed(formatElapsed(startedAt));
      return undefined;
    }
    const interval = setInterval(() => {
      setElapsed(formatElapsed(startedAt));
    }, 1000);
    return () => clearInterval(interval);
  }, [startedAt, running]);

  return <span className="text-xs tabular-nums text-zinc-500">{elapsed}</span>;
}

function formatElapsed(startedAt: number): string {
  const seconds = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}
