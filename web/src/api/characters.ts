import { api } from "./client";

export interface Character {
  book_id: string;
  name: string;
  role: string;
  profile: string;
  personality: string;
  abilities: string[];
  arc_direction: string;
}

export interface Relationship {
  character_a: string;
  character_b: string;
  relation_type: string;
  description: string;
}

export const charactersApi = {
  list: (bookId: string) => api.get<Character[]>(`/api/books/${bookId}/characters`),
  create: (bookId: string, spec: string) => api.post<Character>(`/api/books/${bookId}/characters`, { spec }),
  createBatch: (bookId: string, specs: string[]) => api.post<Character[]>(`/api/books/${bookId}/characters/batch`, { specs }),
  relationships: (bookId: string) => api.get<Relationship[]>(`/api/books/${bookId}/characters/relationships`),
  update: (bookId: string, name: string, updates: Record<string, string>) =>
    api.patch<Character>(`/api/books/${bookId}/characters/${encodeURIComponent(name)}`, { updates })
};
