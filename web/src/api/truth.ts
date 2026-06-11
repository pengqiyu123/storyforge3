import { api } from "./client";

export interface TruthData {
  chapter_no: number;
  source: string;
  fact_assertions: string[];
  character_updates: Record<string, unknown>[];
  relationship_updates: Record<string, unknown>[];
  hook_updates: Record<string, unknown>[];
  irreversible_facts: string[];
  notes: string[];
}

export const truthApi = {
  history: (bookId: string) => api.get<TruthData[]>(`/api/books/${bookId}/truth/history`),
  latest: (bookId: string) => api.get<TruthData | null>(`/api/books/${bookId}/truth/latest`),
  byChapter: (bookId: string, chapterNo: number) => api.get<TruthData | null>(`/api/books/${bookId}/truth/${chapterNo}`),
  extract: (bookId: string, chapterNo: number, text: string) =>
    api.post<TruthData>(`/api/books/${bookId}/truth/extract`, { chapter_no: chapterNo, text })
};
