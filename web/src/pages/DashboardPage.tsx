import { Link } from "react-router-dom";
import { ArrowRight, BookOpen, Clock3, Radio, Sparkles, WandSparkles, Workflow } from "lucide-react";
import type { ComponentType } from "react";
import type { Book } from "@/api/books";
import type { Provider } from "@/api/health";
import { useBooks } from "@/hooks/useBooks";
import { useHealth, useProviders } from "@/hooks/useHealth";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

type IconType = ComponentType<{ className?: string }>;

export function DashboardPage() {
  const { data: books, isLoading: booksLoading } = useBooks();
  const health = useHealth();
  const providers = useProviders();
  const count = books?.length ?? 0;
  const active = books?.filter((book) => book.status === "active").length ?? 0;
  const recentBooks = [...(books ?? [])].sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at)).slice(0, 5);
  const actionBook = recentBooks.find((book) => book.status === "active") ?? recentBooks[0];

  return (
    <div className="space-y-7">
      <section className="grid gap-5 xl:grid-cols-[1.35fr_0.85fr]">
        <div className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-8 shadow-2xl shadow-black/20">
          <p className="text-sm text-amber-200">StoryForge3 Studio</p>
          <h1 className="mt-4 max-w-3xl text-4xl font-semibold leading-tight text-zinc-50">今天的生产状态，一眼看清。</h1>
          <p className="mt-5 max-w-2xl text-sm leading-7 text-zinc-400">
            这里汇总 provider、最近书籍和下一步动作。写作者只需要知道：现在能不能开写，下一本书该从哪里继续。
          </p>
          <div className="mt-7 flex flex-wrap gap-3">
            <Button asChild>
              <Link to="/books">
                打开我的小说
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
            <QuickAction disabled={!actionBook} icon={WandSparkles} label="构建世界观" to={actionBook ? `/books/${actionBook.book_id}?tab=world` : "/books"} />
            <QuickAction disabled={!actionBook} icon={Workflow} label="运行全流程" to={actionBook ? `/books/${actionBook.book_id}?tab=chapters` : "/books"} />
          </div>
        </div>
        <Card>
          <CardHeader>
            <CardTitle>工作区概览</CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            <Metric icon={BookOpen} label="书籍项目" value={count} />
            <Metric icon={Radio} label="连载中" value={active} />
            <Metric icon={Sparkles} label="可用能力" value={11} />
          </CardContent>
        </Card>
      </section>
      <section className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
        <ProviderStatusCard isLoading={health.isLoading || providers.isLoading} providers={providers.data ?? []} />
        <RecentActivityCard books={recentBooks} isLoading={booksLoading} />
      </section>
    </div>
  );
}

function QuickAction({ disabled, icon: Icon, label, to }: { disabled: boolean; icon: IconType; label: string; to: string }) {
  return (
    <Button asChild className={disabled ? "pointer-events-none opacity-50" : undefined} variant="outline">
      <Link aria-disabled={disabled} to={to}>
        <Icon className="h-4 w-4" />
        {label}
      </Link>
    </Button>
  );
}

function Metric({ icon: Icon, label, value }: { icon: IconType; label: string; value: number }) {
  return (
    <div className="flex items-center justify-between rounded-md border border-zinc-800 bg-zinc-900/40 p-4">
      <div className="flex items-center gap-3 text-zinc-400">
        <Icon className="h-4 w-4 text-amber-200" />
        <span className="text-sm">{label}</span>
      </div>
      <span className="text-2xl font-semibold text-zinc-50">{value}</span>
    </div>
  );
}

function ProviderStatusCard({
  isLoading,
  providers
}: {
  isLoading: boolean;
  providers: Provider[];
}) {
  const enabledProviders = providers.filter((provider) => provider.enabled);
  const activeProvider = providers.find((provider) => provider.active) ?? (enabledProviders.length === 1 ? enabledProviders[0] : undefined);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Provider 状态</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading ? (
          <>
            <Skeleton className="h-14" />
            <Skeleton className="h-14" />
          </>
        ) : providers.length ? (
          providers.map((provider) => {
            const isRelayDefault = !provider.model_id.trim();
            const verifiedModel = provider.cc_last_verified_model?.trim();
            return (
              <div key={provider.id} className="flex items-center justify-between gap-4 rounded-md border border-zinc-800 bg-zinc-900/40 p-4">
                <div className="flex min-w-0 items-center gap-3">
                  <span className={provider.enabled ? "h-2.5 w-2.5 shrink-0 rounded-full bg-emerald-300" : "h-2.5 w-2.5 shrink-0 rounded-full bg-zinc-600"} />
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="truncate text-sm font-medium text-zinc-100">{provider.label}</p>
                      {provider.provider_key === activeProvider?.provider_key ? <Badge variant="active">当前</Badge> : null}
                      {isRelayDefault ? <Badge variant="muted">中转站</Badge> : null}
                    </div>
                    <p className="mt-1 truncate text-xs text-zinc-500">{isRelayDefault ? "中转站默认" : provider.model_id}</p>
                    {isRelayDefault && verifiedModel ? <p className="mt-1 truncate text-xs text-zinc-600">已验证：{verifiedModel}</p> : null}
                  </div>
                </div>
                <span className="text-xs text-zinc-500">{provider.enabled ? "在线" : "未配置"}</span>
              </div>
            );
          })
        ) : (
          <p className="rounded-md border border-zinc-800 bg-zinc-900/40 p-4 text-sm text-zinc-500">还没有导入 provider。</p>
        )}
      </CardContent>
    </Card>
  );
}

function RecentActivityCard({ books, isLoading }: { books: Book[]; isLoading: boolean }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>最近活动</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading ? (
          <>
            <Skeleton className="h-14" />
            <Skeleton className="h-14" />
            <Skeleton className="h-14" />
          </>
        ) : books.length ? (
          books.map((book) => (
            <Link
              key={book.book_id}
              className="flex items-center justify-between gap-4 rounded-md border border-zinc-800 bg-zinc-900/40 p-4 transition-colors hover:border-amber-300/30 hover:bg-zinc-900"
              to={`/books/${book.book_id}`}
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-zinc-100">{book.title}</p>
                <p className="mt-1 flex items-center gap-2 text-xs text-zinc-500">
                  <Clock3 className="h-3.5 w-3.5" />
                  {formatActivityTime(book.updated_at)}
                </p>
              </div>
              <Badge variant={book.status === "active" ? "active" : "muted"}>{book.status}</Badge>
            </Link>
          ))
        ) : (
          <p className="rounded-md border border-zinc-800 bg-zinc-900/40 p-4 text-sm text-zinc-500">还没有书籍活动。</p>
        )}
      </CardContent>
    </Card>
  );
}

function formatActivityTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(date);
}
