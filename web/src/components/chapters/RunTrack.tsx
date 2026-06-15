import { Check, Circle, CircleDot, Lock, Minus, XCircle } from "lucide-react";
import type { RunRecord } from "@/api/runs";
import { cn } from "@/lib/utils";

type TrackState = "completed" | "running" | "skipped" | "failed" | "locked";

const RUN_STAGES = [
  { key: "plan", label: "规划", done: ["planned", "drafted", "audited", "needs_revision", "revised", "approved", "truth_committed", "exported"] },
  { key: "draft", label: "起草", done: ["drafted", "audited", "needs_revision", "revised", "approved", "truth_committed", "exported"] },
  { key: "audit", label: "审计", done: ["audited", "needs_revision", "revised", "approved", "truth_committed", "exported"] },
  { key: "revise", label: "修订", done: ["revised", "approved", "truth_committed", "exported"] },
  { key: "approve", label: "批准", done: ["approved", "truth_committed", "exported"] },
  { key: "truth", label: "Truth", done: ["truth_committed", "exported"] },
  { key: "export", label: "导出", done: ["exported"] }
] as const;

interface RunTrackProps {
  chapterStatus: string;
  run: RunRecord | null;
}

export function RunTrack({ chapterStatus, run }: RunTrackProps) {
  const normalizedStatus = chapterStatus.toLowerCase();
  return (
    <div data-testid="run-track" className="rounded-md border border-zinc-800 bg-zinc-950/70 p-3">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
        {RUN_STAGES.map((stage) => {
          const state = stageState(stage.key, stage.done, normalizedStatus, run);
          const Icon = stateIcon(state);
          return (
            <div
              key={stage.key}
              data-testid="run-track-stage"
              data-state={state}
              className={cn(
                "flex min-h-16 items-center gap-2 rounded-md border px-2.5 py-2 text-sm",
                state === "completed" && "border-emerald-400/30 bg-emerald-400/10 text-emerald-200",
                state === "running" && "border-amber-300/40 bg-amber-300/10 text-amber-100",
                state === "skipped" && "border-zinc-700 bg-zinc-900/60 text-zinc-400",
                state === "failed" && "border-red-400/30 bg-red-400/10 text-red-200",
                state === "locked" && "border-zinc-800 bg-zinc-950 text-zinc-600"
              )}
            >
              <span
                className={cn(
                  "flex h-7 w-7 shrink-0 items-center justify-center rounded-full border",
                  state === "running" && "animate-pulse"
                )}
              >
                <Icon className="h-4 w-4" />
              </span>
              <span className="truncate font-medium">{stage.label}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function stageState(stage: string, doneStatuses: readonly string[], chapterStatus: string, run: RunRecord | null): TrackState {
  const result = run?.stage_results?.[stage];
  if (result?.status === "completed") {
    return "completed";
  }
  if (result?.status === "skipped") {
    return "skipped";
  }
  if (result?.status === "failed") {
    return "failed";
  }
  if (result?.status === "running" || (run?.current_stage === stage && (run.status === "running" || run.status === "waiting_for_human"))) {
    return "running";
  }
  if (doneStatuses.includes(chapterStatus)) {
    return "completed";
  }
  return "locked";
}

function stateIcon(state: TrackState) {
  if (state === "completed") {
    return Check;
  }
  if (state === "running") {
    return CircleDot;
  }
  if (state === "skipped") {
    return Minus;
  }
  if (state === "failed") {
    return XCircle;
  }
  if (state === "locked") {
    return Lock;
  }
  return Circle;
}

export function runStageLabel(stage?: string | null): string {
  if (!stage) {
    return "无";
  }
  return RUN_STAGES.find((item) => item.key === stage)?.label ?? stage;
}
