import { api, resolveApiUrl } from "./client";

export interface WorkspaceValidation {
  valid: boolean;
  books_dir: string;
  book_count: number;
  issues: string[];
}

export interface RestoreResult {
  success: boolean;
  book_count: number;
  backup_path: string;
  message: string;
}

interface RestoreEnvelope {
  ok: boolean;
  data: RestoreResult | null;
  error: { code: string; message: string } | null;
}

export const workspaceApi = {
  validate: () => api.get<WorkspaceValidation>("/api/workspace/validate"),
  backup: async () => {
    const response = await fetch(resolveApiUrl("/api/workspace/backup"), { method: "POST" });
    if (!response.ok) {
      throw new Error("工作区备份失败");
    }
    const blob = await response.blob();
    downloadBlob(blob, backupFilename(response.headers.get("content-disposition")));
  },
  restore: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    const response = await fetch(resolveApiUrl("/api/workspace/restore"), { method: "POST", body: form });
    const envelope = (await response.json()) as RestoreEnvelope;
    if (!envelope.ok || !envelope.data) {
      throw new Error(envelope.error?.message || "工作区恢复失败");
    }
    return envelope.data;
  }
};

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function backupFilename(disposition: string | null) {
  const quoted = disposition?.match(/filename="([^"]+)"/)?.[1];
  const plain = disposition?.match(/filename=([^;]+)/)?.[1];
  return quoted || plain || "sf3-backup.zip";
}
