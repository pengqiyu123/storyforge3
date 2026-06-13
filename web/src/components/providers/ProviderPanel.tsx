/**
 * CCSwitch provider panel: list imported providers, switch active, verify, remove,
 * and open the CC-Switch import dialog. Mounted in SettingsPage. Agent-mode-first:
 * the agent/API drives the pipeline; this panel only manages WHICH provider is active.
 */
import { useState } from "react";
import { Download, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import type { ImportedProvider } from "@/api/providers";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useImportedProviders,
  useImportProviders,
  useRemoveProvider,
  useSwitchProvider,
  useVerifyProvider
} from "@/hooks/useProviders";
import { CCImportDialog } from "./CCImportDialog";
import { ProviderCard } from "./ProviderCard";

export function ProviderPanel() {
  const list = useImportedProviders();
  const switchMutation = useSwitchProvider();
  const verifyMutation = useVerifyProvider();
  const removeMutation = useRemoveProvider();
  const [importOpen, setImportOpen] = useState(false);
  const [removeTarget, setRemoveTarget] = useState<ImportedProvider | null>(null);

  async function handleSwitch(key: string, label: string) {
    try {
      await switchMutation.mutateAsync(key);
      toast.success(`已切换到 ${label}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "切换失败");
    }
  }

  async function handleVerify(key: string, label: string) {
    try {
      const res = await verifyMutation.mutateAsync(key);
      if (res.status === "verified") toast.success(`${label} 可用`);
      else toast.error(`${label} 不可用：${res.message ?? "健康检查失败"}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "验证失败");
    }
  }

  async function confirmRemove() {
    if (!removeTarget) return;
    try {
      await removeMutation.mutateAsync(removeTarget.provider_key);
      toast.success(`已移除 ${removeTarget.label}`);
      setRemoveTarget(null);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "移除失败");
    }
  }

  const providers = list.data ?? [];
  return (
    <div className="space-y-5">
      <Card className="border-zinc-800/80 bg-zinc-950/70">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between gap-3">
            <CardTitle className="text-base">AI 供应商</CardTitle>
            <div className="flex items-center gap-2">
              <Button type="button" variant="outline" size="sm" onClick={() => setImportOpen(true)}>
                <Download className="h-4 w-4" />
                导入
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={() => void list.refetch()}>
                <RefreshCw className="h-4 w-4" />
                刷新
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {list.isLoading ? (
            <>
              <Skeleton className="h-20" />
              <Skeleton className="h-20" />
            </>
          ) : providers.length === 0 ? (
            <div className="rounded-md border border-zinc-800 bg-zinc-950/50 p-4">
              <p className="text-sm font-medium text-zinc-200">尚未导入任何供应商</p>
              <p className="mt-1 text-sm text-zinc-500">点击「导入」从 CC-Switch 读取配置。</p>
            </div>
          ) : (
            providers.map((provider) => (
              <ProviderCard
                key={provider.provider_key}
                provider={provider}
                onSwitch={(key) => void handleSwitch(key, provider.label)}
                onVerify={(key) => void handleVerify(key, provider.label)}
                onRemove={(key) =>
                  setRemoveTarget(providers.find((p) => p.provider_key === key) ?? null)
                }
                isSwitching={switchMutation.isPending}
                isVerifying={verifyMutation.isPending}
              />
            ))
          )}
        </CardContent>
      </Card>

      <Dialog
        open={removeTarget !== null}
        onOpenChange={(open) => (!open ? setRemoveTarget(null) : undefined)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认移除</DialogTitle>
            <DialogDescription>
              {removeTarget
                ? `将从 StoryForge3 移除「${removeTarget.label}」（不影响 CC-Switch 中的原始配置，可重新导入）。`
                : ""}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setRemoveTarget(null)}>
              取消
            </Button>
            <Button
              type="button"
              variant="destructive"
              disabled={removeMutation.isPending}
              onClick={() => void confirmRemove()}
            >
              确认移除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <CCImportDialog open={importOpen} onOpenChange={setImportOpen} />
    </div>
  );
}
