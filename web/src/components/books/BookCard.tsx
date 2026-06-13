import { BookOpen, FileText } from "lucide-react";
import { Link } from "react-router-dom";
import { type Book } from "@/api/books";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const statusLabels: Record<string, string> = {
  incubating: "孵化中",
  outlining: "大纲中",
  active: "连载中",
  paused: "暂停",
  completed: "已完结",
  dropped: "归档"
};

function statusVariant(status: string) {
  if (status === "active") return "active";
  if (status === "completed") return "completed";
  if (status === "dropped" || status === "paused") return "archived";
  return "muted";
}

export function BookCard({ book }: { book: Book }) {
  const progress = book.target_chapters > 0 ? Math.min(100, Math.round((book.current_chapter / book.target_chapters) * 100)) : 0;

  return (
    <Link to={`/books/${book.book_id}`} className="block rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-300/50">
      <Card className="group overflow-hidden transition-colors hover:border-amber-300/40 hover:bg-zinc-950">
        <CardHeader className="pb-4">
          <div className="mb-4 flex items-start justify-between gap-4">
            <div className="flex h-11 w-11 items-center justify-center rounded-md border border-zinc-800 bg-zinc-900 text-amber-200">
              <BookOpen className="h-5 w-5" />
            </div>
            <Badge variant={statusVariant(book.status)}>{statusLabels[book.status] ?? book.status}</Badge>
          </div>
          <CardTitle className="line-clamp-2">{book.title}</CardTitle>
          <p className="text-sm text-zinc-500">
            {book.genre} / {book.platform}
          </p>
        </CardHeader>
        <CardContent>
          <div className="mb-4 flex items-center justify-between text-sm">
            <span className="text-zinc-500">章节进度</span>
            <span className="font-medium text-zinc-200">
              {book.current_chapter} / {book.target_chapters} 章
            </span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-zinc-900">
            <div className="h-full rounded-full bg-amber-300 transition-all group-hover:bg-amber-200" style={{ width: `${progress}%` }} />
          </div>
          <div className="mt-5 flex items-center gap-2 text-sm text-zinc-500">
            <FileText className="h-4 w-4" />
            单章目标 {book.chapter_word_count.toLocaleString("zh-CN")} 字
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
