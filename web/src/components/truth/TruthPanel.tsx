import { useMemo, useState } from "react";
import { AlertTriangle, Anchor, FileText, Search, StickyNote, UserCircle, Users } from "lucide-react";
import type { TruthData } from "@/api/truth";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useTruthHistory } from "@/hooks/useTruth";
import { cn } from "@/lib/utils";

interface TruthPanelProps {
  bookId: string;
}

export function TruthPanel({ bookId }: TruthPanelProps) {
  const truthHistory = useTruthHistory(bookId);
  const [activeChapter, setActiveChapter] = useState<number | "all">("all");
  const [search, setSearch] = useState("");
  const history = truthHistory.data ?? [];
  const filtered = useMemo(() => filterTruth(history, search), [history, search]);
  const visible = activeChapter === "all" ? filtered : filtered.filter((item) => item.chapter_no === activeChapter);

  if (truthHistory.isLoading) {
    return <TruthPanelLoading />;
  }

  return (
    <div className="space-y-5">
      <Card className="border-zinc-800/80 bg-zinc-950/70">
        <CardHeader className="pb-3">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
            <div className="space-y-2">
              <CardTitle className="text-base">真相数据</CardTitle>
              <p className="text-sm text-zinc-500">按章节查看连续性事实、角色变化、钩子和不可逆事实。</p>
            </div>
            <label className="relative block w-full max-w-sm">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="搜索事实、角色、钩子"
                className="pl-9"
              />
            </label>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <ChapterPill active={activeChapter === "all"} onClick={() => setActiveChapter("all")}>
              全部
            </ChapterPill>
            {history.map((item) => (
              <ChapterPill
                key={item.chapter_no}
                active={activeChapter === item.chapter_no}
                onClick={() => setActiveChapter(item.chapter_no)}
              >
                第 {item.chapter_no} 章
              </ChapterPill>
            ))}
          </div>
        </CardContent>
      </Card>
      {!visible.length ? (
        <Card className="border-zinc-800/80 bg-zinc-950/50">
          <CardContent className="py-8 text-sm text-zinc-500">
            暂无真相数据。运行章节管线后，真相会在 audit 通过后自动提取。
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {visible.map((truth) => (
            <TruthChapterCard key={truth.chapter_no} truth={truth} />
          ))}
        </div>
      )}
    </div>
  );
}

function TruthPanelLoading() {
  return (
    <div className="space-y-5" data-testid="truth-panel-loading">
      <Card className="border-zinc-800/80 bg-zinc-950/70">
        <CardHeader className="space-y-3">
          <Skeleton className="h-6 w-28" />
          <Skeleton className="h-4 w-80 max-w-full" />
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-10 w-full max-w-sm" />
          <div className="flex gap-2">
            <Skeleton className="h-8 w-16" />
            <Skeleton className="h-8 w-20" />
            <Skeleton className="h-8 w-20" />
          </div>
        </CardContent>
      </Card>
      <Card className="border-zinc-800/80 bg-zinc-950/50">
        <CardContent className="space-y-3 py-5">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </CardContent>
      </Card>
    </div>
  );
}

function TruthChapterCard({ truth }: { truth: TruthData }) {
  return (
    <Card className="border-zinc-800/80 bg-zinc-950/50">
      <CardHeader className="pb-3">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <CardTitle className="text-base">第 {truth.chapter_no} 章</CardTitle>
          <div className="flex flex-wrap gap-2 text-xs text-zinc-500">
            <Badge variant="default">{truth.fact_assertions.length} 事实</Badge>
            <Badge variant="completed">{truth.character_updates.length} 角色</Badge>
            <Badge variant="archived">{truth.hook_updates.length} 钩子</Badge>
            <Badge variant="active">{truth.irreversible_facts.length} 不可逆</Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <TruthSection title="不可逆事实" icon={AlertTriangle} tone="warning" items={truth.irreversible_facts} emptyLabel="本章无不可逆事实。" />
        <TruthSection title="钩子" icon={Anchor} tone="info" items={truth.hook_updates.map(stringifyTruthItem)} emptyLabel="本章无钩子更新。" />
        <TruthSection title="事实断言" icon={FileText} tone="default" items={truth.fact_assertions} emptyLabel="本章无事实断言。" />
        <TruthSection title="角色更新" icon={UserCircle} tone="default" items={truth.character_updates.map(stringifyTruthItem)} emptyLabel="本章无角色更新。" />
        <TruthSection title="关系更新" icon={Users} tone="default" items={truth.relationship_updates.map(stringifyTruthItem)} emptyLabel="本章无关系更新。" />
        <TruthSection title="备注" icon={StickyNote} tone="muted" items={truth.notes} emptyLabel="本章无备注。" />
      </CardContent>
    </Card>
  );
}

function TruthSection({
  title,
  icon: Icon,
  tone,
  items,
  emptyLabel
}: {
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  tone: "warning" | "info" | "default" | "muted";
  items: string[];
  emptyLabel: string;
}) {
  return (
    <section
      className={cn(
        "rounded-md border p-3",
        tone === "warning" && "border-amber-300/30 bg-amber-300/10",
        tone === "info" && "border-sky-300/20 bg-sky-300/10",
        tone === "default" && "border-zinc-800 bg-zinc-950/70",
        tone === "muted" && "border-zinc-900 bg-zinc-950/40"
      )}
    >
      <div className="mb-2 flex items-center gap-2 text-sm font-medium text-zinc-200">
        <Icon className="h-4 w-4 text-amber-200" />
        {title}
      </div>
      {items.length ? (
        <ul className="space-y-2 text-sm text-zinc-300">
          {items.map((item) => (
            <li key={item} className="rounded-md bg-black/20 px-3 py-2 leading-6">
              {item}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-zinc-500">{emptyLabel}</p>
      )}
    </section>
  );
}

function ChapterPill({
  active,
  children,
  onClick
}: {
  active: boolean;
  children: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-full border px-3 py-1.5 text-sm transition-colors",
        active ? "border-amber-300/50 bg-amber-300/10 text-amber-200" : "border-zinc-800 bg-zinc-950 text-zinc-400 hover:text-zinc-200"
      )}
    >
      {children}
    </button>
  );
}

function stringifyTruthItem(item: Record<string, unknown>) {
  return String(item.summary || item.description || item.content || JSON.stringify(item));
}

function filterTruth(history: TruthData[], query: string) {
  if (!query.trim()) {
    return history;
  }
  const lowered = query.trim().toLowerCase();
  return history
    .map((truth) => ({
      ...truth,
      fact_assertions: truth.fact_assertions.filter((item) => item.toLowerCase().includes(lowered)),
      character_updates: truth.character_updates.filter((item) => stringifyTruthItem(item).toLowerCase().includes(lowered)),
      relationship_updates: truth.relationship_updates.filter((item) => stringifyTruthItem(item).toLowerCase().includes(lowered)),
      hook_updates: truth.hook_updates.filter((item) => stringifyTruthItem(item).toLowerCase().includes(lowered)),
      irreversible_facts: truth.irreversible_facts.filter((item) => item.toLowerCase().includes(lowered)),
      notes: truth.notes.filter((item) => item.toLowerCase().includes(lowered))
    }))
    .filter(
      (truth) =>
        truth.fact_assertions.length > 0 ||
        truth.character_updates.length > 0 ||
        truth.relationship_updates.length > 0 ||
        truth.hook_updates.length > 0 ||
        truth.irreversible_facts.length > 0 ||
        truth.notes.length > 0
    );
}
