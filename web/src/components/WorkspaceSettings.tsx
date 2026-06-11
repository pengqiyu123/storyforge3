import { useRef, useState } from "react";
import { Archive, CheckCircle2, FolderCheck, RotateCcw, ShieldAlert, Upload } from "lucide-react";
import { toast } from "sonner";
import { workspaceApi, type RestoreResult, type WorkspaceValidation } from "@/api/workspace";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

export function WorkspaceSettings() {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [validation, setValidation] = useState<WorkspaceValidation | null>(null);
  const [restoreFile, setRestoreFile] = useState<File | null>(null);
  const [restoreResult, setRestoreResult] = useState<RestoreResult | null>(null);
  const [validating, setValidating] = useState(false);
  const [backingUp, setBackingUp] = useState(false);
  const [restoring, setRestoring] = useState(false);

  async function validateWorkspace() {
    setValidating(true);
    try {
      const result = await workspaceApi.validate();
      setValidation(result);
      toast.success(result.valid ? "工作区可用" : "工作区需要检查");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "验证失败");
    } finally {
      setValidating(false);
    }
  }

  async function backupWorkspace() {
    setBackingUp(true);
    try {
      await workspaceApi.backup();
      toast.success("备份已生成");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "备份失败");
    } finally {
      setBackingUp(false);
    }
  }

  async function confirmRestore() {
    if (!restoreFile) {
      return;
    }
    setRestoring(true);
    try {
      const result = await workspaceApi.restore(restoreFile);
      setRestoreResult(result);
      toast.success(result.message);
      setRestoreFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      await validateWorkspace();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "恢复失败");
    } finally {
      setRestoring(false);
    }
  }

  function clearRestoreFile() {
    setRestoreFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  const statusLabel = validation ? (validation.valid ? "可用" : "异常") : "未验证";
  const statusVariant = validation?.valid ? "active" : validation ? "archived" : "muted";

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="pb-4">
          <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
            <div>
              <CardTitle className="flex items-center gap-2 text-base">
                <FolderCheck className="h-4 w-4 text-amber-200" />
                工作区状态
              </CardTitle>
              <CardDescription>检查书籍目录是否存在、可写，以及当前书籍数量。</CardDescription>
            </div>
            <Badge variant={statusVariant}>{statusLabel}</Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2">
            <InfoTile label="工作区路径" value={validation?.books_dir ?? "尚未验证"} />
            <InfoTile label="书籍数量" value={validation ? `${validation.book_count} 本` : "尚未验证"} />
          </div>
          {validation?.issues.length ? (
            <div className="rounded-md border border-red-400/20 bg-red-400/10 p-3 text-sm text-red-200">
              {validation.issues.map((issue) => (
                <p key={issue}>{issue}</p>
              ))}
            </div>
          ) : null}
          <Button type="button" disabled={validating} onClick={() => void validateWorkspace()}>
            <CheckCircle2 className="h-4 w-4" />
            {validating ? "验证中" : "验证"}
          </Button>
        </CardContent>
      </Card>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Archive className="h-4 w-4 text-amber-200" />
              备份
            </CardTitle>
            <CardDescription>将整个 books 目录打包为 zip 文件。</CardDescription>
          </CardHeader>
          <CardContent>
            <Button type="button" disabled={backingUp} onClick={() => void backupWorkspace()}>
              <Archive className="h-4 w-4" />
              {backingUp ? "备份中" : "创建备份"}
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <RotateCcw className="h-4 w-4 text-amber-200" />
              恢复
            </CardTitle>
            <CardDescription>从 zip 备份恢复。恢复前会自动创建当前数据的安全备份。</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Input
              ref={fileInputRef}
              type="file"
              accept=".zip,application/zip"
              aria-label="选择工作区备份文件"
              onChange={(event) => setRestoreFile(event.target.files?.[0] ?? null)}
            />
            <div className="flex items-center gap-2 rounded-md border border-zinc-800 bg-zinc-950/50 px-3 py-2 text-sm text-zinc-400">
              <Upload className="h-4 w-4 text-zinc-500" />
              {restoreFile ? `已选择 ${restoreFile.name}` : "选择 zip 文件后确认恢复"}
            </div>
            {restoreResult ? (
              <div className="rounded-md border border-emerald-400/20 bg-emerald-400/10 p-3 text-sm text-emerald-200">
                <p>{restoreResult.message}</p>
                <p className="mt-1 text-emerald-300/80">安全备份：{restoreResult.backup_path}</p>
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>

      <Dialog open={restoreFile !== null} onOpenChange={(open) => (!open ? clearRestoreFile() : undefined)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ShieldAlert className="h-4 w-4 text-red-300" />
              确认恢复工作区
            </DialogTitle>
            <DialogDescription>
              {restoreFile ? `将使用 ${restoreFile.name} 覆盖当前 books 目录。系统会先创建安全备份。` : ""}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={clearRestoreFile}>
              取消
            </Button>
            <Button type="button" variant="destructive" disabled={restoring} onClick={() => void confirmRestore()}>
              {restoring ? "恢复中" : "确认恢复"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function InfoTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-zinc-800 bg-zinc-950/50 p-4">
      <p className="text-xs text-zinc-500">{label}</p>
      <p className="mt-2 break-all text-sm font-medium text-zinc-200">{value}</p>
    </div>
  );
}
