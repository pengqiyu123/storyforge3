import { Download, RefreshCw, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useUpdate } from "@/contexts/UpdateContext";
import { isTauriEnvironment } from "@/tauriBootstrap";

export function UpdateBanner() {
  const { hasUpdate, updateInfo, isChecking, isUpdating, downloadProgress, error, isDismissed, checkUpdate, dismissUpdate, startUpdate } = useUpdate();

  if (!isTauriEnvironment() || isDismissed || (!hasUpdate && !error)) {
    return null;
  }

  const progressLabel =
    downloadProgress && downloadProgress.total > 0
      ? `${Math.round((downloadProgress.downloaded / downloadProgress.total) * 100)}%`
      : "准备中";

  return (
    <div className="border-b border-amber-300/20 bg-amber-300/10 px-4 py-3 text-sm text-amber-100">
      <div className="mx-auto flex max-w-7xl flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-2 font-medium">
            <Download className="h-4 w-4" />
            {hasUpdate ? `新版本 v${updateInfo?.availableVersion} 可用` : "更新检查失败"}
          </div>
          {updateInfo?.notes ? <p className="line-clamp-2 text-xs text-amber-100/70">{updateInfo.notes}</p> : null}
          {error ? <p className="text-xs text-red-200">{error}</p> : null}
          {isUpdating ? (
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-zinc-900">
              <div
                className="h-full rounded-full bg-amber-300 transition-all"
                style={{ width: downloadProgress?.total ? `${(downloadProgress.downloaded / downloadProgress.total) * 100}%` : "20%" }}
              />
            </div>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {isUpdating ? <span className="text-xs text-amber-100/70">下载 {progressLabel}</span> : null}
          {hasUpdate ? (
            <Button size="sm" disabled={isUpdating} onClick={() => void startUpdate()}>
              立即更新
            </Button>
          ) : (
            <Button size="sm" variant="outline" disabled={isChecking} onClick={() => void checkUpdate()}>
              <RefreshCw className="h-3.5 w-3.5" />
              重试
            </Button>
          )}
          {hasUpdate ? (
            <Button size="sm" variant="ghost" disabled={isUpdating} onClick={dismissUpdate}>
              <X className="h-3.5 w-3.5" />
              忽略
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
