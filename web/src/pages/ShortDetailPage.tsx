import { Link, useParams } from "react-router-dom";
import { ArrowLeft, FileText, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ShortPipeline } from "@/components/shorts/ShortPipeline";
import { useShort, useShorts } from "@/hooks/useShorts";

const statusLabels: Record<string, string> = {
  empty: "未开始",
  planned: "已构思",
  drafted: "已起草",
  audited: "已审计",
  revised: "已修订",
  exported: "已导出"
};

export function ShortDetailPage() {
  const { id = "" } = useParams();
  const storyQuery = useShort(id);
  const storiesQuery = useShorts();
  const meta = storiesQuery.data?.find((story) => story.book_id === id);
  const result = storyQuery.data;

  if (storyQuery.isLoading || storiesQuery.isLoading) {
    return <ShortDetailLoading />;
  }

  if (!result && !meta) {
    return (
      <div className="space-y-4">
        <Button asChild variant="ghost">
          <Link to="/shorts">
            <ArrowLeft className="h-4 w-4" />
            返回短篇小说
          </Link>
        </Button>
        <p className="text-sm text-zinc-500">未找到短篇。</p>
      </div>
    );
  }

  const status = String(result?.status ?? meta?.status ?? "empty");
  const actualChars = meta?.actual_chars ?? 0;
  const targetChars = meta?.target_chars ?? 0;
  const title = meta?.title ?? id;

  return (
    <div className="space-y-7">
      <Button asChild variant="ghost">
        <Link to="/shorts">
          <ArrowLeft className="h-4 w-4" />
          返回短篇小说
        </Link>
      </Button>
      <section className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-6">
        <div className="flex flex-col justify-between gap-5 xl:flex-row xl:items-end">
          <div>
            <p className="text-sm text-amber-200">Short Detail</p>
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <h1 className="text-3xl font-semibold text-zinc-50">{title}</h1>
              <Badge variant="default">{statusLabels[status] ?? status}</Badge>
              {meta?.genre ? <Badge variant="muted">{meta.genre}</Badge> : null}
            </div>
            {meta?.premise ? <p className="mt-3 max-w-3xl text-sm leading-6 text-zinc-400">{meta.premise}</p> : null}
          </div>
          <div className="min-w-64">
            <div className="mb-2 flex justify-between text-sm text-zinc-400">
              <span>字数</span>
              <span>
                {actualChars.toLocaleString("zh-CN")} / {targetChars.toLocaleString("zh-CN")}
              </span>
            </div>
            <div className="h-2 rounded-full bg-zinc-900">
              <div
                className="h-full rounded-full bg-amber-300"
                style={{ width: `${targetChars > 0 ? Math.min(100, Math.round((actualChars / targetChars) * 100)) : 0}%` }}
              />
            </div>
          </div>
        </div>
      </section>
      <div className="grid gap-5 lg:grid-cols-2">
        <MetricCard icon={FileText} label="目标字数" value={`${targetChars.toLocaleString("zh-CN")} 字`} />
        <MetricCard icon={Sparkles} label="下一步" value={nextStepLabel(status)} />
      </div>
      <ShortPipeline bookId={id} title={title} result={result ?? { book_id: id, status, text: "", error: null }} />
    </div>
  );
}

function ShortDetailLoading() {
  return (
    <div className="space-y-7" data-testid="short-detail-loading">
      <Skeleton className="h-9 w-36" />
      <section className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-6">
        <div className="space-y-3">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-9 w-72 max-w-full" />
          <Skeleton className="h-4 w-full max-w-xl" />
        </div>
      </section>
      <Skeleton className="h-96" />
    </div>
  );
}

function MetricCard({ icon: Icon, label, value }: { icon: React.ComponentType<{ className?: string }>; label: string; value: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Icon className="h-4 w-4 text-amber-200" />
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent className="text-2xl font-semibold text-zinc-50">{value}</CardContent>
    </Card>
  );
}

function nextStepLabel(status: string) {
  const labels: Record<string, string> = {
    empty: "构思",
    planned: "起草",
    drafted: "审计",
    audited: "修订",
    revised: "导出",
    exported: "已完成"
  };
  return labels[status] ?? "进入管线";
}
