import { Clock3 } from "lucide-react";
import { ThemeToggle } from "@/components/ui/theme-toggle";

export function Header() {
  return (
    <header className="flex min-h-16 items-center justify-between border-b border-zinc-900 px-5 md:px-8">
      <div>
        <p className="text-xs text-zinc-500">当前工作区</p>
        <p className="text-sm font-medium text-zinc-200">中文网文生产引擎</p>
      </div>
      <div className="flex items-center gap-2">
        <ThemeToggle />
        <div className="flex items-center gap-2 rounded-full border border-zinc-800 px-3 py-1.5 text-xs text-zinc-400">
          <Clock3 className="h-3.5 w-3.5 text-amber-300" />
          写作会话待启动
        </div>
      </div>
    </header>
  );
}
