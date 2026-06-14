/**
 * Import-providers dialog: lists providers available in the CC-Switch DB with
 * multi-select, then POSTs the chosen ids. Spec: cc-switch设计方案.md §3.1.
 * Uses a Check-icon box (no Checkbox dependency) for selection.
 */
import { useState } from "react";
import { Check } from "lucide-react";
import { toast } from "sonner";
import type { CCSwitchProviderInfo } from "@/api/providers";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useAvailableProviders, useImportProviders } from "@/hooks/useProviders";

interface CCImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CCImportDialog({ open, onOpenChange }: CCImportDialogProps) {
  const available = useAvailableProviders(open);
  const importMutation = useImportProviders();
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const providers = available.data?.providers ?? [];
  const importableProviders = providers.filter((provider) => provider.has_api_key);
  const dbAvailable = available.data?.db_available ?? true;
  const allSelected = importableProviders.length > 0 && selected.size === importableProviders.length;

  function toggle(info: CCSwitchProviderInfo) {
    if (!info.has_api_key) return;
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(info.id)) next.delete(info.id);
      else next.add(info.id);
      return next;
    });
  }

  function toggleAll() {
    setSelected(allSelected ? new Set() : new Set(importableProviders.map((p) => p.id)));
  }

  async function handleImport() {
    if (selected.size === 0) return;
    try {
      const res = await importMutation.mutateAsync([...selected]);
      toast.success(`已导入 ${res.imported.length} 个供应商`);
      setSelected(new Set());
      onOpenChange(false);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "导入失败，请重试");
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>从 CC-Switch 导入</DialogTitle>
          <DialogDescription>从本地 CC-Switch 应用选择要导入的供应商配置。</DialogDescription>
        </DialogHeader>
        <div className="flex items-center justify-between">
          <button
            type="button"
            className="flex items-center gap-2 text-sm text-zinc-300 disabled:opacity-50"
            onClick={toggleAll}
            disabled={importableProviders.length === 0}
          >
            <SelectBox checked={allSelected} />
            全选
          </button>
          <span className="text-xs text-zinc-500">
            已选 {selected.size} / {providers.length}
          </span>
        </div>
        <div className="max-h-80 space-y-2 overflow-y-auto">
          {available.isLoading ? (
            <>
              <Skeleton className="h-16" />
              <Skeleton className="h-16" />
            </>
          ) : !dbAvailable ? (
            <p className="rounded-md border border-zinc-800 bg-zinc-950/50 p-4 text-sm text-zinc-500">
              未找到 CC-Switch 数据库，请确认 CC-Switch 已安装并配置了 provider。
            </p>
          ) : providers.length === 0 ? (
            <p className="rounded-md border border-zinc-800 bg-zinc-950/50 p-4 text-sm text-zinc-500">
              CC-Switch 中没有找到可导入的 provider。
            </p>
          ) : (
            providers.map((info) => (
              <ImportRow key={info.id} info={info} checked={selected.has(info.id)} onToggle={() => toggle(info)} />
            ))
          )}
        </div>
        <DialogFooter>
          <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            type="button"
            disabled={selected.size === 0 || importMutation.isPending}
            onClick={() => void handleImport()}
          >
            {importMutation.isPending ? "导入中…" : `导入(${selected.size})`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function SelectBox({ checked }: { checked: boolean }) {
  return (
    <span className="flex h-4 w-4 items-center justify-center rounded border border-zinc-600 bg-zinc-900">
      {checked ? <Check className="h-3 w-3 text-emerald-300" /> : null}
    </span>
  );
}

function ImportRow({
  info,
  checked,
  onToggle
}: {
  info: CCSwitchProviderInfo;
  checked: boolean;
  onToggle: () => void;
}) {
  const isRelay = !info.model_id.trim();
  const canImport = info.has_api_key;
  return (
    <button
      type="button"
      onClick={onToggle}
      disabled={!canImport}
      className={`flex w-full items-start gap-3 rounded-md border p-3 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-55 ${
        checked ? "border-amber-300/40 bg-amber-300/5" : "border-zinc-800 bg-zinc-950/50 enabled:hover:border-zinc-700"
      }`}
    >
      <span className="mt-0.5">
        <SelectBox checked={checked} />
      </span>
      <div className="min-w-0 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className="truncate text-sm font-medium text-zinc-100">{info.label || info.provider_key}</p>
          {info.cc_is_current ? <Badge variant="active">当前使用</Badge> : null}
          {info.cc_health?.is_healthy === false ? <Badge variant="archived">异常</Badge> : null}
          {!canImport ? <Badge variant="archived">无密钥</Badge> : null}
          {isRelay ? <Badge variant="muted">中转站</Badge> : null}
          {info.cc_api_format ? <Badge variant="muted">{info.cc_api_format}</Badge> : null}
        </div>
        <p className="truncate text-xs text-zinc-500">
          {info.base_url || "—"} · {info.model_id || "中转站默认"}
          {info.has_api_key && info.api_key_preview ? ` · ${info.api_key_preview}` : ""}
        </p>
      </div>
    </button>
  );
}
