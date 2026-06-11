import { api } from "./client";

export type FanficMode = "canon" | "au" | "ooc" | "cp";

export interface FanficCanon {
  book_id: string;
  source_name: string;
  mode: FanficMode | string;
  world_rules: string;
  character_profiles: string;
  key_events: string;
  power_system: string;
  writing_style: string;
  full_document: string;
  generated_at: string;
}

export interface CanonImportRequest {
  source_text: string;
  source_name: string;
  mode: FanficMode | string;
}

export const fanficApi = {
  importCanon: (bookId: string, data: CanonImportRequest) => api.post<FanficCanon>(`/api/books/${bookId}/fanfic/import`, data),
  getCanon: (bookId: string) => api.get<FanficCanon>(`/api/books/${bookId}/fanfic/canon`),
  refreshCanon: (bookId: string, data: CanonImportRequest) => api.post<FanficCanon>(`/api/books/${bookId}/fanfic/refresh`, data)
};
