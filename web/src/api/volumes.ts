import { api } from "./client";

export interface VolumeOutline {
  book_id: string;
  volume_no: number;
  title: string;
  chapter_count: number;
  synopsis: string;
  key_scenes: string[];
  rhythm_curve: string[];
}

export interface UpdateVolumeRequest {
  title: string;
  chapter_count: number;
  synopsis: string;
  key_scenes: string[];
  rhythm_curve: string[];
}

export const volumesApi = {
  list: (bookId: string) => api.get<VolumeOutline[]>(`/api/books/${bookId}/volumes`),
  plan: (bookId: string, volumeCount: number, totalChapters: number) =>
    api.post<VolumeOutline[]>(`/api/books/${bookId}/volumes`, { volume_count: volumeCount, total_chapters: totalChapters }),
  get: (bookId: string, volumeNo: number) => api.get<VolumeOutline>(`/api/books/${bookId}/volumes/${volumeNo}`),
  update: (bookId: string, volumeNo: number, outline: UpdateVolumeRequest) =>
    api.put<VolumeOutline>(`/api/books/${bookId}/volumes/${volumeNo}`, outline)
};
