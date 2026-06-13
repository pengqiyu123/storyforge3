/**
 * One imported-provider row: identity, health badge, and switch/verify/remove actions.
 * Row layout adapted from SnapshotPanel; content modelled on cc-switch-main's ProviderCard.
 * Click the row (when not active) to switch active provider.
 */
import { ShieldCheck, Trash2 } from "lucide-react";
import type { ImportedProvider } from "@/api/providers";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { HealthBadge } from "./HealthBadge";

interface ProviderCardProps {
  provider: ImportedProvider;
  onSwitch: (providerKey: string) => void;
  onVerify: (providerKey: string) => void;
  onRemove: (providerKey: string) => void;
  isSwitching?: boolean;
  isVerifying?: boolean;
}

function formatLabel(format?: string | null): string {
  switch (format) {
    case "openai_chat":
      return "chat";
    case "openai_responses":
      return "responses";
    case "anthropic":
      return "anthropic";
    case "gemini_native":
      return "gemini";
    default:
      return format ?? "";
  }
}

export function ProviderCard({ provider, onSwitch, onVerify, onRemove, isSwitching, isVerifying }: ProviderCardProps) {
  const isActive = provider.active;
  const isRelay = !provider.model_id.trim();
  return (
    <div className="flex flex-col gap-3 rounded-md border border-zinc-800 bg-zinc-950/50 p-4 sm:flex-row sm:items-center sm:justify-between">
      <button
        type="button"
        className="flex min-w-0 flex-1 items-center gap-3 text-left disabled:cursor-not-allowed"
        disabled={isActive || isSwitching}
        onClick={() => {
          if (!isActive) onSwitch(provider.provider_key);
        }}
        aria-label={isActive ? `当前使用 ${provider.label}` : `切换到 ${provider.label}`}
      >
        <span
          className={
            provider.enabled
              ? "h-2.5 w-2.5 shrink-0 rounded-full bg-emerald-300"
              : "h-2.5 w-2.5 shrink-0 rounded-full bg-zinc-600"
          }
        />
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate text-sm font-medium text-zinc-100">{provider.label}</p>
            {isActive ? <Badge variant="active">当前使用</Badge> : null}
            {provider.cc_api_format ? <Badge variant="muted">{formatLabel(provider.cc_api_format)}</Badge> : null}
            {isRelay ? <Badge variant="muted">中转站</Badge> : null}
          </div>
          <p className="truncate text-xs text-zinc-500">
            {provider.base_url || "—"} · {provider.model_id || "中转站默认"}
            {provider.api_key ? ` · ${provider.api_key}` : ""}
          </p>
          <HealthBadge status={provider.cc_probe_status} message={provider.cc_probe_message} />
        </div>
      </button>
      <div className="flex shrink-0 items-center gap-2">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={isVerifying}
          onClick={() => onVerify(provider.provider_key)}
          aria-label={`验证 ${provider.label}`}
        >
          <ShieldCheck className="h-4 w-4" />
          验证
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => onRemove(provider.provider_key)}
          aria-label={`移除 ${provider.label}`}
        >
          <Trash2 className="h-4 w-4" />
          移除
        </Button>
      </div>
    </div>
  );
}
