import type { Book } from "@/api/books";
import type { ChapterConsistency } from "@/api/reconcile";
import type { VolumeOutline } from "@/api/volumes";
import { useReconcile } from "@/hooks/useReconcile";
import { useVolumes } from "@/hooks/useVolumes";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ChapterCard } from "./ChapterCard";

export function ChapterList({ book }: { book: Book }) {
  const reconcile = useReconcile(book.book_id);
  const volumes = useVolumes(book.book_id);
  const reconciliation = reconcile.data;
  const chapters = (reconciliation?.chapters ?? []).filter(hasAnyArtifact);
  const maxChapter = reconciliation?.max_chapter ?? 0;
  const nextWritableChapter = reconciliation?.next_writable_chapter_no ?? maxChapter + 1;
  const blockingChapterNos = (reconciliation?.chapters ?? [])
    .filter((chapter) => chapter.status === "inconsistent")
    .map((chapter) => chapter.chapter_no);
  const groups = buildChapterGroups(chapters, volumes.data);

  if (reconcile.isLoading) {
    return <ChapterListLoading />;
  }

  if (reconcile.error) {
    return (
      <div className="rounded-lg border border-red-400/20 bg-red-400/10 p-4 text-sm text-red-200">
        章节产物诊断读取失败。请稍后重试。
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-zinc-800 bg-zinc-950/50 p-4 text-sm">
        <span className="font-medium text-zinc-200">
          已发现章节产物 {chapters.length} 章 · 最高第 {maxChapter} 章
          {reconciliation?.has_blocking_inconsistency ? ` · ⚠ ${reconciliation.inconsistent_count} 章数据不一致` : ""}
        </span>
      </div>
      {groups.length
        ? groups.map((group) => <ChapterGroup key={group.key} bookId={book.book_id} group={group} />)
        : chapters.map((chapter) => <ChapterCard key={chapter.chapter_no} bookId={book.book_id} chapter={chapter} />)}
      <NextChapterIndicator
        chapterNo={nextWritableChapter}
        hasBlockingInconsistency={Boolean(reconciliation?.has_blocking_inconsistency)}
        blockingChapterNos={blockingChapterNos}
      />
    </div>
  );
}

function ChapterListLoading() {
  return (
    <div className="space-y-4" data-testid="chapter-list-loading">
      <Skeleton className="h-14 w-full" />
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-24 w-full" />
    </div>
  );
}

function NextChapterIndicator({
  chapterNo,
  hasBlockingInconsistency,
  blockingChapterNos
}: {
  chapterNo: number;
  hasBlockingInconsistency: boolean;
  blockingChapterNos: number[];
}) {
  if (hasBlockingInconsistency) {
    return (
      <Card className="border-amber-300/30 bg-amber-300/10 p-4">
        <p className="text-sm font-medium text-amber-100">
          ⚠ 存在数据不一致（{formatChapterNos(blockingChapterNos)}），请先检查后再继续生产
        </p>
      </Card>
    );
  }
  return (
    <Card className="border-dashed border-zinc-700 bg-zinc-950/40 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm font-medium text-zinc-200">下一章：第 {chapterNo} 章</p>
        <p className="text-sm text-zinc-500">尚未产生章节产物，由 agent/API 启动生产</p>
      </div>
    </Card>
  );
}

interface ChapterGroupData {
  key: string;
  volume?: VolumeOutline;
  chapters: ChapterConsistency[];
}

function ChapterGroup({ bookId, group }: { bookId: string; group: ChapterGroupData }) {
  if (!group.volume) {
    return (
      <div className="space-y-4" data-testid={group.key}>
        {group.chapters.map((chapter) => (
          <ChapterCard key={chapter.chapter_no} bookId={bookId} chapter={chapter} />
        ))}
      </div>
    );
  }

  return (
    <section className="space-y-3" data-testid={`chapter-volume-${group.volume.volume_no}`}>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-800 pb-2">
        <h3 className="text-sm font-medium text-zinc-200">
          第 {group.volume.volume_no} 卷：{group.volume.title}
        </h3>
        <span className="text-xs text-zinc-500">{group.chapters.length} 章</span>
      </div>
      <div className="space-y-4">
        {group.chapters.map((chapter) => (
          <ChapterCard key={chapter.chapter_no} bookId={bookId} chapter={chapter} />
        ))}
      </div>
    </section>
  );
}

function buildChapterGroups(chapters: ChapterConsistency[], volumes?: VolumeOutline[]): ChapterGroupData[] {
  if (!volumes?.length || !chapters.length) {
    return [];
  }

  const sortedVolumes = [...volumes].sort((left, right) => left.volume_no - right.volume_no);
  const groups: ChapterGroupData[] = [];
  let startChapter = 1;
  const remaining = new Map(chapters.map((chapter) => [chapter.chapter_no, chapter]));

  for (const volume of sortedVolumes) {
    const endChapter = startChapter + Math.max(0, volume.chapter_count) - 1;
    const volumeChapters = chapters.filter((chapter) => chapter.chapter_no >= startChapter && chapter.chapter_no <= endChapter);
    for (const chapter of volumeChapters) {
      remaining.delete(chapter.chapter_no);
    }
    if (volumeChapters.length) {
      groups.push({ key: `volume-${volume.volume_no}`, volume, chapters: volumeChapters });
    }
    startChapter = endChapter + 1;
  }

  const unassigned = [...remaining.values()].sort((left, right) => left.chapter_no - right.chapter_no);
  if (unassigned.length) {
    groups.push({ key: "chapter-volume-unassigned", chapters: unassigned });
  }

  return groups;
}

function hasAnyArtifact(chapter: ChapterConsistency): boolean {
  return chapter.has_text || chapter.has_plan || chapter.has_truth || chapter.has_export || chapter.has_state || chapter.has_run;
}

function formatChapterNos(chapterNos: number[]): string {
  if (!chapterNos.length) {
    return "未知章节";
  }
  return `第 ${chapterNos.sort((left, right) => left - right).join("、")} 章`;
}
