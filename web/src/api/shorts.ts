import { api } from "./client";
import type { AuditResult } from "./chapters";

export type ShortStoryStatus = "empty" | "planned" | "drafted" | "audited" | "revised" | "exported";

export interface ShortStoryMeta {
  book_id: string;
  title: string;
  genre: string;
  status: ShortStoryStatus | string;
  target_chars: number;
  premise: string;
  style: string;
  actual_chars: number;
  created_at: string;
  updated_at: string;
}

export interface ShortStoryPlan {
  book_id: string;
  premise: string;
  opening: string;
  climax: string;
  ending: string;
  characters: string;
  key_scenes: string[];
  must_keep: string[];
  must_avoid: string[];
}

export interface ShortStoryResult {
  book_id: string;
  status: ShortStoryStatus | string;
  text: string;
  error?: string | null;
}

export interface CreateShortRequest {
  title: string;
  genre: string;
  target_chars?: number;
  premise?: string;
  style?: string;
}

export const shortStoriesApi = {
  list: () => api.get<ShortStoryMeta[]>("/api/short-stories"),
  create: (data: CreateShortRequest) => api.post<ShortStoryMeta>("/api/short-stories", data),
  get: (bookId: string) => api.get<ShortStoryResult>(`/api/short-stories/${bookId}`),
  plan: (bookId: string) => api.post<ShortStoryPlan>(`/api/short-stories/${bookId}/plan`, {}),
  draft: (bookId: string) => api.post<{ text: string }>(`/api/short-stories/${bookId}/draft`, {}),
  audit: (bookId: string) => api.post<AuditResult>(`/api/short-stories/${bookId}/audit`, {}),
  revise: (bookId: string) => api.post<ShortStoryResult>(`/api/short-stories/${bookId}/revise`, {}),
  export: (bookId: string, fmt = "tomato_txt") => api.post<{ path: string }>(`/api/short-stories/${bookId}/export`, { fmt }),
  runFullPipeline: (bookId: string) => api.post<ShortStoryResult>(`/api/short-stories/${bookId}/run`, {})
};
