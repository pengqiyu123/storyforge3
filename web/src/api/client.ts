import { isTauriEnvironment } from "@/tauriBootstrap";

const WEB_API_BASE = import.meta.env.VITE_API_URL || "";
const DESKTOP_API_BASE = "http://127.0.0.1:8000";

interface ApiEnvelope<T> {
  ok: boolean;
  data: T | null;
  error: { code: string; message: string } | null;
}

export function resolveApiUrl(path: string): string {
  const apiBase = isTauriEnvironment() ? DESKTOP_API_BASE : WEB_API_BASE;
  return `${apiBase}${path}`;
}

const EXPORT_EXTENSIONS: Record<string, string[]> = {
  tomato_txt: ["txt"],
  tomato: ["txt"],
  txt: ["txt"],
  md: ["md"],
  epub: ["epub"],
  qidian_txt: ["txt"]
};

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(resolveApiUrl(path), {
    headers: { "Content-Type": "application/json" },
    ...options
  });

  const envelope = (await response.json()) as ApiEnvelope<T>;
  if (!envelope.ok) {
    throw new Error(envelope.error?.message || "请求失败");
  }
  return envelope.data as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, {
      method: "POST",
      body: JSON.stringify(body)
    }),
  put: <T>(path: string, body: unknown) =>
    request<T>(path, {
      method: "PUT",
      body: JSON.stringify(body)
    }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, {
      method: "PATCH",
      body: JSON.stringify(body)
    })
};

export async function exportChapterDesktop(bookId: string, chapterNo: number, fmt: string, chapterTitle: string): Promise<string | null> {
  if (!isTauriEnvironment()) {
    return null;
  }

  const [{ save }, { writeFile }] = await Promise.all([import("@tauri-apps/plugin-dialog"), import("@tauri-apps/plugin-fs")]);
  const extensions = EXPORT_EXTENSIONS[fmt] ?? ["txt"];
  const filePath = await save({
    defaultPath: `${safeFilename(chapterTitle || `第${chapterNo}章`)}.${extensions[0]}`,
    filters: [{ name: fmt.toUpperCase(), extensions }]
  });

  if (!filePath) {
    return null;
  }

  const exported = await api.post<{ path: string }>(`/api/books/${bookId}/chapters/${chapterNo}/export`, { fmt });
  const filename = exportedFilename(exported.path);
  const response = await fetch(resolveApiUrl(`/api/books/${bookId}/exports/${encodeURIComponent(filename)}`));
  if (!response.ok) {
    throw new Error(`导出文件下载失败: ${response.status}`);
  }

  const bytes = new Uint8Array(await response.arrayBuffer());
  await writeFile(filePath, bytes);
  return filePath;
}

export async function exportShortDesktop(bookId: string, fmt: string, title: string): Promise<string | null> {
  if (!isTauriEnvironment()) {
    return null;
  }

  const [{ save }, { writeFile }] = await Promise.all([import("@tauri-apps/plugin-dialog"), import("@tauri-apps/plugin-fs")]);
  const extensions = EXPORT_EXTENSIONS[fmt] ?? ["txt"];
  const filePath = await save({
    defaultPath: `${safeFilename(title || "短篇小说")}.${extensions[0]}`,
    filters: [{ name: fmt.toUpperCase(), extensions }]
  });

  if (!filePath) {
    return null;
  }

  const exported = await api.post<{ path: string }>(`/api/short-stories/${bookId}/export`, { fmt });
  const filename = exportedFilename(exported.path);
  const response = await fetch(resolveApiUrl(`/api/books/${bookId}/exports/${encodeURIComponent(filename)}`));
  if (!response.ok) {
    throw new Error(`导出文件下载失败: ${response.status}`);
  }

  const bytes = new Uint8Array(await response.arrayBuffer());
  await writeFile(filePath, bytes);
  return filePath;
}

function exportedFilename(path: string): string {
  const parts = path.split(/[\\/]/).filter(Boolean);
  return parts.at(-1) || path;
}

function safeFilename(value: string): string {
  return value.replace(/[<>:"/\\|?*\u0000-\u001F]/g, "_").trim() || "chapter";
}
