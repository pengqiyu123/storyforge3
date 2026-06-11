import { FileText, Hash } from "lucide-react";
import { Link } from "react-router-dom";
import type { ShortStoryMeta } from "@/api/shorts";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const statusLabels: Record<string, string> = {
  empty: "未开始",
  planned: "已构思",
  drafted: "已起草",
  audited: "已审计",
  revised: "已修订",
  exported: "已导出"
};

function statusVariant(status: string) {
  if (status === "exported") return "active";
  if (status === "revised") return "completed";
  if (status === "audited") return "archived";
  if (status === "drafted" || status === "planned") return "default";
  return "muted";
}

export function ShortCard({ story }: { story: ShortStoryMeta }) {
  const progress = story.target_chars > 0 ? Math.min(100, Math.round((story.actual_chars / story.target_chars) * 100)) : 0;

  return (
    <Link to={`/shorts/${story.book_id}`} className="block rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-300/50">
      <Card className="group overflow-hidden transition-colors hover:border-amber-300/40 hover:bg-zinc-950">
        <CardHeader className="pb-4">
          <div className="mb-4 flex items-start justify-between gap-4">
            <div className="flex h-11 w-11 items-center justify-center rounded-md border border-zinc-800 bg-zinc-900 text-amber-200">
              <FileText className="h-5 w-5" />
            </div>
            <Badge variant={statusVariant(String(story.status))}>{statusLabels[String(story.status)] ?? story.status}</Badge>
          </div>
          <CardTitle className="line-clamp-2">{story.title}</CardTitle>
          <p className="text-sm text-zinc-500">{story.genre}</p>
        </CardHeader>
        <CardContent>
          <div className="mb-4 flex items-center justify-between text-sm">
            <span className="text-zinc-500">字数</span>
            <span className="font-medium text-zinc-200">
              {story.actual_chars.toLocaleString("zh-CN")} / {story.target_chars.toLocaleString("zh-CN")}
            </span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-zinc-900">
            <div className="h-full rounded-full bg-amber-300 transition-all group-hover:bg-amber-200" style={{ width: `${progress}%` }} />
          </div>
          <div className="mt-5 flex items-center gap-2 text-sm text-zinc-500">
            <Hash className="h-4 w-4" />
            更新于 {formatDate(story.updated_at)}
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

function formatDate(value: string) {
  if (!value) {
    return "未知";
  }
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}
