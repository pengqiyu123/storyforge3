import { api } from "./client";

export interface SnapshotMeta {
  book_id: string;
  chapter_no: number;
  timestamp: string;
  file_count: number;
  path: string;
}

export interface RestoreResult {
  restored_files: string[];
  count: number;
}

export const snapshotsApi = {
  list: (bookId: string) => api.get<SnapshotMeta[]>(`/api/books/${bookId}/snapshots`),
  restore: (bookId: string, snapshotPath: string) =>
    api.post<RestoreResult>(`/api/books/${bookId}/snapshots/${encodeURIComponent(snapshotPath)}/restore`, {})
};
