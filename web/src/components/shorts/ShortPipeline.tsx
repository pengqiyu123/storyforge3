import { useState } from "react";
import { toast } from "sonner";
import { Check, Play } from "lucide-react";
import { exportShortDesktop } from "@/api/client";
import type { AuditResult } from "@/api/chapters";
import type { ShortStoryResult } from "@/api/shorts";
import { AuditResultPanel } from "@/components/chapters/AuditResultPanel";
import { ChapterEditor } from "@/components/editor/ChapterEditor";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useShortAudit, useShortDraft, useShortExport, useShortPlan, useShortRevise, useShortRunFull } from "@/hooks/useShorts";
import { countChineseChars } from "@/lib/utils";
import { isTauriEnvironment } from "@/tauriBootstrap";

interface ShortPipelineProps {
  bookId: string;
  title?: string;
  result?: ShortStoryResult | null;
}

const steps = [
  { key: "plan", label: "构思", done: ["planned", "drafted", "audited", "revised", "exported"] },
  { key: "draft", label: "起草", done: ["drafted", "audited", "revised", "exported"] },
  { key: "audit", label: "审计", done: ["audited", "revised", "exported"] },
  { key: "revise", label: "修订", done: ["revised", "exported"] },
  { key: "export", label: "导出", done: ["exported"] }
] as const;

export function ShortPipeline({ bookId, title = "短篇小说", result }: ShortPipelineProps) {
  const plan = useShortPlan(bookId);
  const draft = useShortDraft(bookId);
  const audit = useShortAudit(bookId);
  const revise = useShortRevise(bookId);
  const exportShort = useShortExport(bookId);
  const runFull = useShortRunFull(bookId);
  const [lastAudit, setLastAudit] = useState<AuditResult | null>(null);
  const [lastError, setLastError] = useState("");
  const [exportFormat, setExportFormat] = useState("tomato_txt");
  const isBusy = [plan, draft, audit, revise, exportShort, runFull].some((mutation) => mutation.isPending);
  const status = String(result?.status ?? "empty").toLowerCase();
  const text = result?.text ?? "";

  async function runAction(label: string, action: () => Promise<unknown>) {
    try {
      const value = await action();
      if (isAuditResult(value)) {
        setLastAudit(value);
      }
      setLastError("");
      if (value !== null) {
        toast.success(`${label}完成`);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : `${label}失败`;
      const detail = `${label}失败: ${message}`;
      setLastError(detail);
      window.setTimeout(() => setLastError(""), 3000);
      toast.error(message);
    }
  }

  async function runExport() {
    if (isTauriEnvironment()) {
      return exportShortDesktop(bookId, exportFormat, title);
    }
    return exportShort.mutateAsync([exportFormat]);
  }

  const actions: Record<string, () => Promise<unknown>> = {
    plan: () => plan.mutateAsync([]),
    draft: () => draft.mutateAsync([]),
    audit: () => audit.mutateAsync([]),
    revise: () => revise.mutateAsync([]),
    export: runExport
  };

  return (
    <Card className="border-zinc-800/80 bg-zinc-950/80">
      <CardHeader>
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
          <CardTitle>短篇管线</CardTitle>
          <span className="text-sm text-zinc-500">状态：{status}</span>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
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
          <Button disabled={isBusy} onClick={() => runAction("一键运行", () => runFull.mutateAsync([]))}>
            <Play className="h-4 w-4" />
            一键运行
          </Button>
          <label className="flex items-center gap-2 text-sm text-zinc-500">
            格式
            <select
              value={exportFormat}
              onChange={(event) => setExportFormat(event.target.value)}
              className="h-9 rounded-md border border-zinc-800 bg-zinc-950 px-3 text-sm text-zinc-100 outline-none focus:border-amber-300/70"
            >
              <option value="tomato_txt">番茄 TXT</option>
              <option value="txt">TXT</option>
              <option value="md">Markdown</option>
              <option value="epub">EPUB</option>
              <option value="qidian_txt">起点 TXT</option>
            </select>
          </label>
        </div>
        {lastError ? <p className="rounded-md border border-red-400/20 bg-red-400/10 p-3 text-sm text-red-300">{lastError}</p> : null}
        <AuditResultPanel result={lastAudit} />
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-zinc-300">正文预览</span>
            <span className="text-xs text-zinc-500">{countChineseChars(text)} 字</span>
          </div>
          <ChapterEditor value={text} readOnly placeholder="等待起草..." className="h-72" />
        </div>
      </CardContent>
    </Card>
  );
}

function isAuditResult(value: unknown): value is AuditResult {
  return Boolean(value && typeof value === "object" && "passed" in value && "blocking_issues" in value && "warnings" in value);
}
