import { AlertTriangle, FolderOpen, RotateCw } from "lucide-react";
import { openPath } from "@tauri-apps/plugin-opener";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface StartupErrorScreenProps {
  error: string;
}

export function StartupErrorScreen({ error }: StartupErrorScreenProps) {
  function retry() {
    window.location.reload();
  }

  async function openLogs() {
    const { dataDir, join } = await import("@tauri-apps/api/path");
    await openPath(await join(await dataDir(), "storyforge3", "logs"));
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-zinc-950 px-6">
      <Card className="w-full max-w-2xl border-red-400/25 bg-zinc-950/95">
        <CardHeader className="space-y-4 text-center">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full border border-red-400/30 bg-red-400/10 text-red-300">
            <AlertTriangle className="h-7 w-7" />
          </div>
          <CardTitle className="text-2xl">StoryForge3 启动失败</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="rounded-md border border-zinc-800 bg-zinc-900/70 p-4">
            <p className="text-sm text-zinc-400">Python API 未能启动</p>
            <p className="mt-2 break-words text-sm text-red-200">{error}</p>
          </div>
          <div className="grid gap-2 text-sm text-zinc-400 sm:grid-cols-3">
            <span>检查虚拟环境</span>
            <span>检查 8000 端口</span>
            <span>检查依赖安装</span>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row sm:justify-center">
            <Button onClick={retry}>
              <RotateCw className="h-4 w-4" />
              重试
            </Button>
            <Button variant="outline" onClick={() => void openLogs()}>
              <FolderOpen className="h-4 w-4" />
              查看日志
            </Button>
          </div>
        </CardContent>
      </Card>
    </main>
  );
}
