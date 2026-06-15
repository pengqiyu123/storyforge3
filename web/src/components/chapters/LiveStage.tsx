import { useState } from "react";
import { AlertTriangle, Ban, Clock, Radio, Square } from "lucide-react";
import type { RunRecord } from "@/api/runs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { runStageLabel } from "./RunTrack";

interface LiveStageProps {
  run: RunRecord | null;
  onCancel?: (runId: string) => Promise<unknown> | unknown;
  isCancelling?: boolean;
}

const ACTIVE_RUN_STATUSES = new Set(["running", "waiting_for_human"]);

export function LiveStage({ run, onCancel, isCancelling = false }: LiveStageProps) {
  const [localCancelling, setLocalCancelling] = useState(false);
  const canCancel = Boolean(run && ACTIVE_RUN_STATUSES.has(run.status) && onCancel);
  const stage = run?.live?.stage ?? run?.current_stage ?? null;
  const progress = run?.live?.progress;
  const streamText = run?.live?.streamText ?? "";
  const errorMessage = run?.live?.errorMessage ?? run?.error_message ?? "";
  const waitingMessage = run?.live?.waitingMessage ?? "";
  const cancelling = isCancelling || localCancelling;

  async function handleCancel() {
    if (!run || !onCancel || cancelling) {
      return;
    }
    setLocalCancelling(true);
    try {
      await onCancel(run.run_id);
    } finally {
      setLocalCancelling(false);
    }
  }

  if (!run) {
    return (
      <section data-testid="live-stage" className="rounded-md border border-zinc-800 bg-zinc-950/70 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="flex h-8 w-8 items-center justify-center rounded-full border border-zinc-700 text-zinc-500">
              <Radio className="h-4 w-4" />
            </span>
            <div>
              <p className="text-sm font-medium text-zinc-200">空闲</p>
              <p className="text-xs text-zinc-500">由 agent 触发生产</p>
            </div>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section data-testid="live-stage" className="rounded-md border border-zinc-800 bg-zinc-950/70 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <span
            className={cn(
              "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border",
              run.status === "running" && "border-amber-300/40 text-amber-200",
              run.status === "waiting_for_human" && "border-sky-300/40 text-sky-200",
              run.status === "failed" && "border-red-400/40 text-red-200",
              run.status === "resumable" && "border-orange-300/40 text-orange-200",
              (run.status === "completed" || run.status === "cancelled") && "border-zinc-700 text-zinc-400"
            )}
          >
            {run.status === "failed" || run.status === "resumable" ? <AlertTriangle className="h-4 w-4" /> : <Clock className="h-4 w-4" />}
          </span>
          <div className="min-w-0 space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={badgeVariant(run.status)}>{run.status.toUpperCase()}</Badge>
              <span className="text-sm font-medium text-zinc-200">{runStageLabel(stage)}</span>
              <span className="text-xs text-zinc-500">由 agent 驱动</span>
            </div>
            {progress ? (
              <div className="flex items-center gap-2 text-xs text-zinc-400">
                <span>{`${progress.completed}/${progress.total}`}</span>
                <span className="h-1.5 w-28 overflow-hidden rounded-full bg-zinc-800">
                  <span
                    className="block h-full rounded-full bg-amber-300"
                    style={{ width: `${progress.total > 0 ? Math.min(100, (progress.completed / progress.total) * 100) : 0}%` }}
                  />
                </span>
              </div>
            ) : null}
          </div>
        </div>

        {canCancel ? (
          <Button variant="destructive" size="sm" disabled={cancelling} onClick={handleCancel}>
            <Square className="h-4 w-4" />
            取消
          </Button>
        ) : null}
      </div>

      {waitingMessage ? (
        <p className="mt-3 rounded-md border border-sky-400/20 bg-sky-400/10 p-3 text-sm text-sky-200">{waitingMessage}</p>
      ) : null}

      {errorMessage ? (
        <div className="mt-3 rounded-md border border-red-400/20 bg-red-400/10 p-3 text-sm text-red-200">
          <p>{errorMessage}</p>
          {run.status === "resumable" && run.resume_from ? <p className="mt-1 text-xs text-red-200/80">可从 {runStageLabel(run.resume_from)} 恢复</p> : null}
        </div>
      ) : null}

      {streamText ? (
        <div className="mt-3 rounded-md border border-zinc-800 bg-zinc-900/50 p-3 text-sm leading-7 text-zinc-200">
          {streamText
            .split(/\n\s*\n/)
            .filter(Boolean)
            .map((paragraph, index) => (
              <p key={`${index}-${paragraph.slice(0, 12)}`}>{paragraph}</p>
            ))}
        </div>
      ) : null}

      {!streamText && !waitingMessage && !errorMessage && run.status === "completed" ? (
        <p className="mt-3 text-sm text-zinc-500">最近运行完成</p>
      ) : null}

      {run.status === "cancelled" ? (
        <p className="mt-3 flex items-center gap-2 text-sm text-zinc-500">
          <Ban className="h-4 w-4" />
          已取消
        </p>
      ) : null}
    </section>
  );
}

function badgeVariant(status: string): "default" | "active" | "completed" | "archived" | "muted" {
  if (status === "running" || status === "waiting_for_human") {
    return "active";
  }
  if (status === "completed") {
    return "completed";
  }
  if (status === "failed" || status === "resumable") {
    return "archived";
  }
  return "muted";
}
