import { api } from "./client";

export type RunStatus = "pending" | "running" | "waiting_for_human" | "completed" | "failed" | "resumable" | "cancelled";

export type StageRunStatus = "pending" | "running" | "completed" | "skipped" | "failed" | string;

export interface StageResult {
  stage: string;
  status: StageRunStatus;
  started_at: string;
  finished_at?: string | null;
  duration_ms?: number | null;
  error_code?: string | null;
  error_message?: string | null;
  summary?: Record<string, unknown> | null;
}

export interface RunLiveState {
  stage?: string | null;
  message?: string;
  progress?: { completed: number; total: number } | null;
  streamText?: string;
  waitingMessage?: string;
  errorMessage?: string;
}

export interface RunRecord {
  run_id: string;
  book_id: string;
  chapter_no: number;
  mode: string;
  target_stages: string[];
  status: RunStatus;
  current_stage: string | null;
  started_at: string;
  updated_at: string;
  stage_results: Record<string, StageResult>;
  llm_calls: Record<string, unknown>[];
  error_code?: string | null;
  error_message?: string | null;
  resume_from?: string | null;
  live?: RunLiveState;
}

export const runsApi = {
  get: (bookId: string, chapterNo: number) => api.get<RunRecord>(`/api/books/${bookId}/chapters/${chapterNo}/run`),
  cancel: (bookId: string, chapterNo: number, runId: string) =>
    api.post<RunRecord>(`/api/books/${bookId}/chapters/${chapterNo}/run/${runId}/cancel`, {})
};
