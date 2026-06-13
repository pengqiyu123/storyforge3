import { ProviderPanel } from "@/components/providers/ProviderPanel";
import { WorkspaceSettings } from "@/components/WorkspaceSettings";

export function SettingsPage() {
  return (
    <div className="space-y-8">
      <div>
        <p className="text-sm text-amber-200">Workspace</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-normal text-zinc-50">设置</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-zinc-400">
          管理 AI 供应商、验证和恢复本地创作数据。
        </p>
      </div>
      <ProviderPanel />
      <WorkspaceSettings />
    </div>
  );
}
