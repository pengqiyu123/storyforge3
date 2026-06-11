import { CreateShortDialog } from "@/components/shorts/CreateShortDialog";
import { ShortList } from "@/components/shorts/ShortList";
import { useCreateShort, useShorts } from "@/hooks/useShorts";

export function ShortsPage() {
  const stories = useShorts();
  const createShort = useCreateShort();

  return (
    <div className="space-y-8">
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div>
          <p className="text-sm text-amber-200">Short Desk</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-normal text-zinc-50">短篇小说</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-zinc-400">管理独立短篇的构思、起草、审计、修订和导出。</p>
        </div>
        <CreateShortDialog isPending={createShort.isPending} onCreate={(data) => createShort.mutateAsync(data)} />
      </div>
      {stories.error ? <p className="rounded-md border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200">{stories.error.message}</p> : null}
      <ShortList stories={stories.data} isLoading={stories.isLoading} />
    </div>
  );
}
