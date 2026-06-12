import { AlertCircle, LoaderCircle } from "lucide-react";
import { cn } from "@/lib/utils";

interface PipelineProgressProps {
  stage: string;
  progress?: {
    completed: number;
    total: number;
  } | null;
  active: boolean;
  error?: string | null;
}

export function PipelineProgress({ stage, progress, active, error }: PipelineProgressProps) {
  if (!active) {
    return null;
  }

  if (error) {
    return (
      <div
        data-testid="pipeline-progress"
        className="rounded-md border border-red-400/20 bg-red-400/10 p-3 text-sm text-red-200"
      >
        <div className="flex items-center gap-2 font-medium text-red-300">
          <AlertCircle className="h-4 w-4" />
          {stage ? `${stage}失败` : "管线失败"}
        </div>
        <p className="mt-1 text-xs text-red-200/90">{error}</p>
      </div>
    );
  }

  const completed = progress?.completed ?? 0;
  const total = progress?.total ?? 0;
  const determinate = total > 0 && completed >= 0;
  const percentage = determinate ? Math.min(100, Math.max(0, (completed / total) * 100)) : 20;

  return (
    <div
      data-testid="pipeline-progress"
      className="rounded-md border border-zinc-800/80 bg-zinc-950/80 p-3 text-sm text-zinc-200"
    >
      <div className="flex items-center gap-2 font-medium text-zinc-100">
        <LoaderCircle className="h-4 w-4 animate-spin" />
        <span>{`正在${stage}...`}</span>
      </div>
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-zinc-800" data-testid="pipeline-progress-track">
        <div
          data-testid="pipeline-progress-bar"
          className={cn(
            "h-full rounded-full bg-blue-500 transition-[width] duration-300",
            determinate ? "" : "animate-pulse"
          )}
          style={{ width: `${percentage}%` }}
        />
      </div>
      {determinate ? (
        <div className="mt-2 flex items-center justify-between text-xs text-zinc-400">
          <span>{`${completed}/${total} 段`}</span>
          <span>{`正在生成第 ${completed}/${total} 段`}</span>
        </div>
      ) : (
        <p className="mt-2 text-xs text-zinc-400">正在生成...</p>
      )}
    </div>
  );
}
