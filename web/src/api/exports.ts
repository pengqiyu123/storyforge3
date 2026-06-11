import { resolveApiUrl } from "./client";

export interface ExportBookRequest {
  fmt?: string;
  approved_only?: boolean;
}

export const exportsApi = {
  exportBook: (bookId: string, data: ExportBookRequest = {}) =>
    fetch(resolveApiUrl(`/api/books/${bookId}/export`), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fmt: data.fmt ?? "tomato_txt", approved_only: data.approved_only ?? true })
    }),
  getExportFile: (bookId: string, filename: string) => fetch(resolveApiUrl(`/api/books/${bookId}/exports/${encodeURIComponent(filename)}`))
};
