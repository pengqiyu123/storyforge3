import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { StartupErrorScreen } from "@/components/StartupErrorScreen";
import { UpdateBanner } from "@/components/UpdateBanner";
import { UpdateProvider } from "@/contexts/UpdateContext";
import { DashboardPage } from "@/pages/DashboardPage";
import { BooksPage } from "@/pages/BooksPage";
import { BookDetailPage } from "@/pages/BookDetailPage";
import { ShortsPage } from "@/pages/ShortsPage";
import { ShortDetailPage } from "@/pages/ShortDetailPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { getStartupError, isTauriEnvironment, STARTUP_ERROR_EVENT } from "@/tauriBootstrap";

export function App() {
  const [startupError, setStartupError] = useState(() => getStartupError());

  useEffect(() => {
    if (!isTauriEnvironment()) {
      return;
    }

    const handler = (event: Event) => {
      setStartupError((event as CustomEvent<string>).detail || getStartupError());
    };
    window.addEventListener(STARTUP_ERROR_EVENT, handler);
    return () => window.removeEventListener(STARTUP_ERROR_EVENT, handler);
  }, []);

  if (startupError) {
    return <StartupErrorScreen error={startupError} />;
  }

  const routes = (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<DashboardPage />} />
        <Route path="books" element={<BooksPage />} />
        <Route path="books/:id" element={<BookDetailPage />} />
        <Route path="shorts" element={<ShortsPage />} />
        <Route path="shorts/:id" element={<ShortDetailPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );

  if (!isTauriEnvironment()) {
    return routes;
  }

  return (
    <UpdateProvider>
      <UpdateBanner />
      {routes}
    </UpdateProvider>
  );
}
