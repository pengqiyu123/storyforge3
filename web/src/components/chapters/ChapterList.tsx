import type { Book } from "@/api/books";
import { ChapterCard } from "./ChapterCard";

export function ChapterList({ book }: { book: Book }) {
  const visibleCount = Math.min(Math.max(book.current_chapter + 2, 5), book.target_chapters || 5);
  const chapters = Array.from({ length: visibleCount }, (_, index) => index + 1);

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-4 text-sm text-zinc-400">
        当前显示前 {visibleCount} 章。后续阶段会加入分页和批量筛选。
      </div>
      {chapters.map((chapterNo) => (
        <ChapterCard key={chapterNo} bookId={book.book_id} chapterNo={chapterNo} />
      ))}
    </div>
  );
}
