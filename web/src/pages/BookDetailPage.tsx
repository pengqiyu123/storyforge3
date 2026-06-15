import { Link, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, BookOpen, GitBranch, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { WorldEditor } from "@/components/world/WorldEditor";
import { CharacterList } from "@/components/characters/CharacterList";
import { VolumeList } from "@/components/volumes/VolumeList";
import { ChapterList } from "@/components/chapters/ChapterList";
import { SnapshotPanel } from "@/components/snapshots/SnapshotPanel";
import { TruthPanel } from "@/components/truth/TruthPanel";
import { useBook } from "@/hooks/useBooks";
import { useReconcile } from "@/hooks/useReconcile";
import { useBuildWorld, useUpdateWorld, useWorld } from "@/hooks/useWorld";
import { useCharacterRelationships, useCharacters, useCreateCharacter } from "@/hooks/useCharacters";
import { usePlanVolumes, useVolumes } from "@/hooks/useVolumes";

export function BookDetailPage() {
  const { id = "" } = useParams();
  const [searchParams] = useSearchParams();
  const initialTab = validTab(searchParams.get("tab"));
  const bookQuery = useBook(id);
  const world = useWorld(id);
  const buildWorld = useBuildWorld(id);
  const updateWorld = useUpdateWorld(id);
  const characters = useCharacters(id);
  const relationships = useCharacterRelationships(id);
  const createCharacter = useCreateCharacter(id);
  const volumes = useVolumes(id);
  const planVolumes = usePlanVolumes(id);
  const book = bookQuery.data;
  const reconcile = useReconcile(book?.book_id);
  const progressChapter = reconcile.data?.max_chapter ?? book?.current_chapter ?? 0;

  if (bookQuery.isLoading) {
    return <BookDetailLoading />;
  }

  if (!book) {
    return (
      <div className="space-y-4">
        <Button asChild variant="ghost">
          <Link to="/books">
            <ArrowLeft className="h-4 w-4" />
            返回我的小说
          </Link>
        </Button>
        <p className="text-sm text-zinc-500">未找到书籍。</p>
      </div>
    );
  }

  return (
    <div className="space-y-7">
      <Button asChild variant="ghost">
        <Link to="/books">
          <ArrowLeft className="h-4 w-4" />
          返回我的小说
        </Link>
      </Button>
      <section className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-6">
        <div className="flex flex-col justify-between gap-5 xl:flex-row xl:items-end">
          <div>
            <p className="text-sm text-amber-200">Book Detail</p>
            <h1 className="mt-2 text-3xl font-semibold text-zinc-50">{book.title}</h1>
            <p className="mt-3 text-sm text-zinc-500">
              {book.genre} / {book.platform} / {book.status}
            </p>
          </div>
          <div className="min-w-64">
            <div className="mb-2 flex justify-between text-sm text-zinc-400">
              <span>章节进度</span>
              <span>
                {progressChapter} / {book.target_chapters}
              </span>
            </div>
            <div className="h-2 rounded-full bg-zinc-900">
              <div
                className="h-full rounded-full bg-amber-300"
                style={{ width: `${Math.min(100, Math.round((progressChapter / Math.max(1, book.target_chapters)) * 100))}%` }}
              />
            </div>
          </div>
        </div>
      </section>
      <Tabs defaultValue={initialTab}>
        <TabsList>
          <TabsTrigger value="overview">概览</TabsTrigger>
          <TabsTrigger value="world">世界观</TabsTrigger>
          <TabsTrigger value="characters">角色</TabsTrigger>
          <TabsTrigger value="volumes">卷规划</TabsTrigger>
          <TabsTrigger value="chapters">章节</TabsTrigger>
          <TabsTrigger value="truth">真相</TabsTrigger>
          <TabsTrigger value="snapshots">快照</TabsTrigger>
        </TabsList>
        <TabsContent value="overview">
          <OverviewTab book={book} progressChapter={progressChapter} />
        </TabsContent>
        <TabsContent value="world">
          <WorldEditor
            bookId={id}
            genre={book.genre}
            world={world.data}
            isLoading={world.isLoading}
            onBuild={(data) => buildWorld.mutateAsync(data)}
            onUpdate={(data) => updateWorld.mutateAsync(data)}
            isPending={buildWorld.isPending || updateWorld.isPending}
          />
        </TabsContent>
        <TabsContent value="characters">
          <CharacterList
            characters={characters.data}
            relationships={relationships.data}
            isLoading={characters.isLoading}
            onCreate={(spec) => createCharacter.mutateAsync(spec)}
            isPending={createCharacter.isPending}
          />
        </TabsContent>
        <TabsContent value="volumes">
          <VolumeList
            volumes={volumes.data}
            isLoading={volumes.isLoading}
            onPlan={(data) => planVolumes.mutateAsync(data)}
            isPending={planVolumes.isPending}
          />
        </TabsContent>
        <TabsContent value="chapters">
          <ChapterList book={book} />
        </TabsContent>
        <TabsContent value="truth">
          <TruthPanel bookId={id} />
        </TabsContent>
        <TabsContent value="snapshots">
          <SnapshotPanel bookId={id} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function BookDetailLoading() {
  return (
    <div className="space-y-7" data-testid="book-detail-loading">
      <Skeleton className="h-9 w-36" />
      <section className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-6">
        <div className="flex flex-col justify-between gap-5 xl:flex-row xl:items-end">
          <div className="space-y-3">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-9 w-72 max-w-full" />
            <Skeleton className="h-4 w-48" />
          </div>
          <div className="min-w-64 space-y-3">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-2 w-full" />
          </div>
        </div>
      </section>
      <Skeleton className="h-11 w-full max-w-xl" />
      <div className="grid gap-5 lg:grid-cols-3">
        <Skeleton className="h-32" />
        <Skeleton className="h-32" />
        <Skeleton className="h-32" />
      </div>
    </div>
  );
}

function OverviewTab({ book, progressChapter }: { book: { target_chapters: number; chapter_word_count: number }; progressChapter: number }) {
  return (
    <div className="grid gap-5 lg:grid-cols-3">
      <OverviewCard icon={BookOpen} label="当前章节" value={`${progressChapter} / ${book.target_chapters} 章`} />
      <OverviewCard icon={Sparkles} label="单章字数" value={`${book.chapter_word_count.toLocaleString("zh-CN")} 字`} />
      <OverviewCard icon={GitBranch} label="下一步" value="进入章节管线" />
    </div>
  );
}

function validTab(value: string | null) {
  return value && ["overview", "world", "characters", "volumes", "chapters", "truth", "snapshots"].includes(value) ? value : "overview";
}

function OverviewCard({ icon: Icon, label, value }: { icon: React.ComponentType<{ className?: string }>; label: string; value: string }) {
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
