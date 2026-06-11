import { Outlet } from "react-router-dom";
import { FocusModeProvider, useFocusMode } from "@/hooks/useFocusMode";
import { Header } from "./Header";
import { Sidebar } from "./Sidebar";
import { cn } from "@/lib/utils";

export function AppLayout() {
  return (
    <FocusModeProvider>
      <AppShell />
    </FocusModeProvider>
  );
}

function AppShell() {
  const { enabled } = useFocusMode();

  return (
    <div className={cn("min-h-screen bg-[#080807] text-zinc-100 transition-colors duration-300", enabled && "bg-black")}>
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(circle_at_20%_10%,rgba(245,158,11,0.10),transparent_26%),linear-gradient(120deg,rgba(39,39,42,0.35),transparent_40%)]" />
      <div className="relative flex min-h-screen">
        <Sidebar focusMode={enabled} />
        <div className="flex min-w-0 flex-1 flex-col">
          <Header />
          <main className={cn("flex-1 px-5 py-6 transition-[padding] duration-300 md:px-8", enabled && "md:px-14 lg:px-20 xl:px-28")}>
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}
