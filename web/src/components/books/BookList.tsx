import { BookCard } from "./BookCard";
import { Skeleton } from "@/components/ui/skeleton";
import { type Book } from "@/api/books";

interface BookListProps {
  books: Book[] | undefined;
  isLoading: boolean;
}

export function BookList({ books, isLoading }: BookListProps) {
  if (isLoading) {
    return (
      <div className="grid gap-5 lg:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 3 }).map((_, index) => (
          <Skeleton key={index} className="h-64" />
        ))}
      </div>
    );
  }

  if (!books?.length) {
    return (
      <div className="rounded-lg border border-dashed border-zinc-800 bg-zinc-950/40 p-10 text-center">
        <p className="text-lg font-medium text-zinc-200">还没有小说项目</p>
        <p className="mt-2 text-sm text-zinc-500">创建第一本书后，就可以进入世界观、角色和章节生产流程。</p>
      </div>
    );
  }

  return (
    <div className="grid gap-5 lg:grid-cols-2 xl:grid-cols-3">
      {books.map((book) => (
        <BookCard key={book.book_id} book={book} />
      ))}
    </div>
  );
}
