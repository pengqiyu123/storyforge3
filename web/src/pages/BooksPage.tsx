import { CreateBookDialog } from "@/components/books/CreateBookDialog";
import { BookList } from "@/components/books/BookList";
import { useBooks, useCreateBook } from "@/hooks/useBooks";

export function BooksPage() {
  const books = useBooks();
  const createBook = useCreateBook();

  return (
    <div className="space-y-8">
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div>
          <p className="text-sm text-amber-200">Book Desk</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-normal text-zinc-50">我的小说</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-zinc-400">管理正在孵化、连载和收尾的长篇项目。</p>
        </div>
        <CreateBookDialog isPending={createBook.isPending} onCreate={(data) => createBook.mutateAsync(data)} />
      </div>
      {books.error ? <p className="rounded-md border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200">{books.error.message}</p> : null}
      <BookList books={books.data} isLoading={books.isLoading} />
    </div>
  );
}
