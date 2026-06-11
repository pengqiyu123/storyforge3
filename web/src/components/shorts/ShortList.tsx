import type { ShortStoryMeta } from "@/api/shorts";
import { Skeleton } from "@/components/ui/skeleton";
import { ShortCard } from "./ShortCard";

interface ShortListProps {
  stories: ShortStoryMeta[] | undefined;
  isLoading: boolean;
}

export function ShortList({ stories, isLoading }: ShortListProps) {
  if (isLoading) {
    return (
      <div className="grid gap-5 lg:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 3 }).map((_, index) => (
          <Skeleton key={index} className="h-64" />
        ))}
      </div>
    );
  }

  if (!stories?.length) {
    return (
      <div className="rounded-lg border border-dashed border-zinc-800 bg-zinc-950/40 p-10 text-center">
        <p className="text-lg font-medium text-zinc-200">还没有短篇小说</p>
        <p className="mt-2 text-sm text-zinc-500">点击上方创建第一篇。</p>
      </div>
    );
  }

  return (
    <div className="grid gap-5 lg:grid-cols-2 xl:grid-cols-3">
      {stories.map((story) => (
        <ShortCard key={story.book_id} story={story} />
      ))}
    </div>
  );
}
