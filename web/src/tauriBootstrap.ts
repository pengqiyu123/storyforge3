declare global {
  interface Window {
    __TAURI_INTERNALS__?: unknown;
  }
}

interface WaitForApiReadyOptions {
  maxRetries?: number;
  retryDelayMs?: number;
}

const STARTUP_ERROR_STORAGE_KEY = "storyforge3:startupError";
export const STARTUP_ERROR_EVENT = "storyforge3:startup-error";

export function isTauriEnvironment(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export function recordStartupError(error: string): void {
  sessionStorage.setItem(STARTUP_ERROR_STORAGE_KEY, error);
  window.dispatchEvent(new CustomEvent<string>(STARTUP_ERROR_EVENT, { detail: error }));
}

export function getStartupError(): string | null {
  return sessionStorage.getItem(STARTUP_ERROR_STORAGE_KEY);
}

export function clearStartupError(): void {
  sessionStorage.removeItem(STARTUP_ERROR_STORAGE_KEY);
}

export async function listenForStartupErrors(): Promise<(() => void) | undefined> {
  if (!isTauriEnvironment()) {
    return undefined;
  }

  const { listen } = await import("@tauri-apps/api/event");
  return listen<string>("python-startup-error", (event) => {
    recordStartupError(event.payload);
  });
}

export async function waitForApiReady(options: WaitForApiReadyOptions = {}): Promise<void> {
  if (!isTauriEnvironment()) {
    return;
  }

  const maxRetries = options.maxRetries ?? 60;
  const retryDelayMs = options.retryDelayMs ?? 500;

  for (let attempt = 0; attempt < maxRetries; attempt += 1) {
    try {
      const response = await fetch("http://127.0.0.1:8000/api/health");
      if (response.ok) {
        clearStartupError();
        return;
      }
    } catch {
      // Desktop startup races the Python child process; retry until the health endpoint is ready.
    }

    await new Promise((resolve) => setTimeout(resolve, retryDelayMs));
  }

  recordStartupError(`Python API health check timed out after ${maxRetries} attempts.`);
}
