import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { App } from "@/App";
import { Toaster } from "@/components/ui/sonner";
import "@/globals.css";
import { listenForStartupErrors, waitForApiReady } from "@/tauriBootstrap";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false
    }
  }
});

void listenForStartupErrors().then((unlisten) => {
  window.addEventListener("beforeunload", () => unlisten?.(), { once: true });
});

waitForApiReady().then(() => {
  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <App />
          <Toaster />
        </BrowserRouter>
      </QueryClientProvider>
    </React.StrictMode>
  );
});
