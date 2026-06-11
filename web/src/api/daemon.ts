import { api } from "./client";

export interface DaemonStartRequest {
  max_chapters_per_run?: number;
  max_consecutive_failures?: number;
  chapter_interval_seconds?: number;
  start_from_chapter?: number;
  target_chapters?: number;
}

export const daemonApi = {
  start: (bookId: string, data: DaemonStartRequest = {}) => api.post<{ status: string; book_id: string }>(`/api/books/${bookId}/daemon/start`, data)
};
