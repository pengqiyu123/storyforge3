import { BookOpen, FileText, LayoutDashboard, PenLine, Settings } from "lucide-react";
import { NavLink } from "react-router-dom";
import { cn } from "@/lib/utils";

const items = [
  { to: "/", label: "仪表盘", icon: LayoutDashboard },
  { to: "/books", label: "我的小说", icon: BookOpen },
  { to: "/shorts", label: "短篇", icon: FileText },
  { to: "/settings", label: "设置", icon: Settings }
];

export function Sidebar({ focusMode = false }: { focusMode?: boolean }) {
  return (
    <aside
      className={cn(
        "hidden min-h-screen w-64 shrink-0 overflow-hidden border-r border-zinc-900 bg-black/30 px-5 py-6 transition-[width,padding,opacity] duration-300 ease-out md:block",
        focusMode && "md:w-0 md:px-0 md:opacity-0"
      )}
      data-testid="app-sidebar"
    >
      <div className="mb-9 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-md bg-amber-300 text-zinc-950">
          <PenLine className="h-5 w-5" />
        </div>
        <div>
          <p className="text-base font-semibold text-zinc-50">StoryForge3</p>
          <p className="text-xs text-zinc-500">长篇生产台</p>
        </div>
      </div>
      <nav className="space-y-1">
        {items.map((item) => (
          <NavLink
            key={item.to}
            end={item.to === "/"}
            to={item.to}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-md px-3 py-2.5 text-sm text-zinc-400 transition-colors hover:bg-zinc-900 hover:text-zinc-100",
                isActive && "bg-zinc-900 text-amber-200"
              )
            }
          >
            <item.icon className="h-4 w-4" />
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
