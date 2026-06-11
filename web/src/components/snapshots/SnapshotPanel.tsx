import { useState } from "react";
import { RefreshCw, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import type { SnapshotMeta } from "@/api/snapshots";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useSnapshotList, useSnapshotRestore } from "@/hooks/useSnapshots";

interface SnapshotPanelProps {
  bookId: string;
}

export function SnapshotPanel({ bookId }: SnapshotPanelProps) {
  const snapshotList = useSnapshotList(bookId);
  const restore = useSnapshotRestore(bookId);
  // Adapted from BackupListSection's confirmFilename flow: keep one pending destructive target in local state.
  const [selected, setSelected] = useState<SnapshotMeta | null>(null);

  async function confirmRestore() {
    if (!selected) {
      return;
    }
    try {
      await restore.mutateAsync(selected.path);
      toast.success("快照已恢复");
      setSelected(null);
    } catch (error) {
      const message = error instanceof Error ? error.message : "回滚失败";
      toast.error(message);
    }
  }

  if (snapshotList.isLoading) {
    return <SnapshotPanelLoading />;
  }

  const snapshots = snapshotList.data ?? [];
  return (
    <div className="space-y-5">
      <Card className="border-zinc-800/80 bg-zinc-950/70">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between gap-3">
            <CardTitle className="text-base">版本快照</CardTitle>
            <Button type="button" variant="outline" size="sm" onClick={() => void snapshotList.refetch()}>
              <RefreshCw className="h-4 w-4" />
              刷新
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {!snapshots.length ? (
            <div className="rounded-md border border-zinc-800 bg-zinc-950/50 p-4">
              <p className="text-sm font-medium text-zinc-200">暂无快照</p>
              <p className="mt-1 text-sm text-zinc-500">快照在导出时自动创建（最多保留 5 份）。</p>
            </div>
          ) : (
            snapshots.map((snapshot) => (
              <div key={snapshot.path} className="flex flex-col gap-3 rounded-md border border-zinc-800 bg-zinc-950/50 p-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="space-y-1">
                  <p className="text-sm font-medium text-zinc-200">{formatSnapshotTime(snapshot.timestamp)}</p>
                  <p className="text-sm text-zinc-500">
                    第 {snapshot.chapter_no} 章 · {snapshot.file_count} 文件
                  </p>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  aria-label={`回滚第 ${snapshot.chapter_no} 章快照`}
                  onClick={() => setSelected(snapshot)}
                >
                  <RotateCcw className="h-4 w-4" />
                  回滚
                </Button>
              </div>
            ))
          )}
        </CardContent>
      </Card>
      <Dialog open={selected !== null} onOpenChange={(open) => (!open ? setSelected(null) : undefined)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认回滚</DialogTitle>
            <DialogDescription>
              {selected
                ? `将恢复“${formatSnapshotTime(selected.timestamp)} 第 ${selected.chapter_no} 章”快照中的章节正文和状态。当前正文和状态将被覆盖。此操作不可撤销。`
                : ""}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setSelected(null)}>
              取消
            </Button>
            <Button type="button" variant="destructive" disabled={restore.isPending} onClick={() => void confirmRestore()}>
              确认回滚
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function SnapshotPanelLoading() {
  return (
    <Card className="border-zinc-800/80 bg-zinc-950/70" data-testid="snapshot-panel-loading">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-3">
          <Skeleton className="h-6 w-24" />
          <Skeleton className="h-8 w-16" />
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
      </CardContent>
    </Card>
  );
}

// Adapted from BackupListSection's formatBackupDate helper, simplified to StoryForge's local timestamp display.
function formatSnapshotTime(timestamp: string) {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return timestamp;
  }
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  });
}
