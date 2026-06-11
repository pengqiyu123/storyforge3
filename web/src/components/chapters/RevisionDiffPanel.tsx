import { FileDiff, Plus, X } from "lucide-react";
import type { RevisionDiff, RevisionDiffBlock } from "@/api/chapters";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface RevisionDiffPanelProps {
  diff: RevisionDiff;
  onClose?: () => void;
}

export function RevisionDiffPanel({ diff, onClose }: RevisionDiffPanelProps) {
  const { summary, blocks } = diff;

  if (!blocks.length) {
    return null;
  }

  return (
    <Card data-testid="revision-diff-panel" className="border-zinc-800/80 bg-black/25">
      <CardHeader className="pb-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <FileDiff className="h-4 w-4 text-emerald-300" />
              修订变更
            </CardTitle>
            <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-500">
              {summary.changed_blocks > 0 ? <Badge variant="archived">改动 {summary.changed_blocks} 段</Badge> : null}
              {summary.added_blocks > 0 ? <Badge variant="active">新增 {summary.added_blocks} 段</Badge> : null}
              {summary.removed_blocks > 0 ? <Badge variant="default">删除 {summary.removed_blocks} 段</Badge> : null}
              <span>
                {summary.before_chars} → {summary.after_chars} 字
              </span>
            </div>
          </div>
          {onClose ? (
            <Button type="button" variant="ghost" size="icon" aria-label="关闭修订变更" className="h-8 w-8" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          ) : null}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {blocks.map((block, index) => (
          <DiffBlockView key={`${block.kind}-${index}`} block={block} />
        ))}
      </CardContent>
    </Card>
  );
}

function DiffBlockView({ block }: { block: RevisionDiffBlock }) {
  const hasBefore = block.kind === "replace" || block.kind === "delete";
  const hasAfter = block.kind === "replace" || block.kind === "insert";

  return (
    <div className="space-y-2 rounded-md border border-zinc-900 bg-zinc-950/60 p-3">
      <div className="flex items-center gap-2 text-xs text-zinc-500">
        <Badge variant={block.kind === "insert" ? "active" : block.kind === "delete" ? "default" : "archived"}>
          {kindLabel(block.kind)}
        </Badge>
        {block.kind === "insert" ? <Plus className="h-3.5 w-3.5 text-emerald-300" /> : null}
      </div>
      <div className="grid gap-2 lg:grid-cols-2">
        <DiffPane title="修订前" text={block.before_text} emptyLabel="（无）" tone={hasBefore ? "before" : "empty"} />
        <DiffPane title="修订后" text={block.after_text} emptyLabel="（删除）" tone={hasAfter ? "after" : "empty"} />
      </div>
    </div>
  );
}

function DiffPane({
  title,
  text,
  emptyLabel,
  tone
}: {
  title: string;
  text: string;
  emptyLabel: string;
  tone: "before" | "after" | "empty";
}) {
  return (
    <div
      className={cn(
        "rounded-md border p-3",
        tone === "before" && "border-red-400/30 bg-red-400/10 text-red-100",
        tone === "after" && "border-emerald-400/30 bg-emerald-400/10 text-emerald-100",
        tone === "empty" && "border-zinc-800 bg-zinc-900/50 text-zinc-500"
      )}
    >
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-zinc-400">{title}</p>
      {text ? (
        <pre className="whitespace-pre-wrap font-sans text-sm leading-6">{text}</pre>
      ) : (
        <p className="text-sm italic">{emptyLabel}</p>
      )}
    </div>
  );
}

function kindLabel(kind: RevisionDiffBlock["kind"]) {
  if (kind === "insert") {
    return "新增";
  }
  if (kind === "delete") {
    return "删除";
  }
  return "替换";
}
