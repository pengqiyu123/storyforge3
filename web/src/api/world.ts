import { api } from "./client";

export interface WorldConfig {
  book_id: string;
  setting: string;
  power_system: string;
  core_conflict: string;
  rules: string[];
}

export const worldApi = {
  get: (bookId: string) => api.get<WorldConfig>(`/api/books/${bookId}/world`),
  build: (bookId: string, genre: string, seedBrief: string) =>
    api.post<WorldConfig>(`/api/books/${bookId}/world`, { genre, seed_brief: seedBrief }),
  update: (bookId: string, world: Omit<WorldConfig, "book_id">) => api.put<WorldConfig>(`/api/books/${bookId}/world`, world)
};
