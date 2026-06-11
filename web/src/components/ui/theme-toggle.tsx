import { Focus, PanelLeftClose } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useFocusMode } from "@/hooks/useFocusMode";

export function ThemeToggle() {
  const { enabled, toggle } = useFocusMode();
  const label = enabled ? "关闭专注模式" : "开启专注模式";

  return (
    <Button
      aria-label={label}
      aria-pressed={enabled}
      className="border-zinc-800 bg-black/20 text-zinc-300 hover:bg-zinc-900 hover:text-amber-200"
      onClick={toggle}
      size="sm"
      title={label}
      type="button"
      variant="outline"
    >
      {enabled ? <PanelLeftClose className="h-3.5 w-3.5" /> : <Focus className="h-3.5 w-3.5" />}
      <span className="hidden sm:inline">{enabled ? "退出专注" : "专注模式"}</span>
    </Button>
  );
}
