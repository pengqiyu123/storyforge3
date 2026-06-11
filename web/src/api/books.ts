import { api } from "./client";

export interface Book {
  book_id: string;
  title: string;
  genre: string;
  platform: string;
  status: string;
  target_chapters: number;
  chapter_word_count: number;
  current_chapter: number;
  created_at: string;
  updated_at: string;
}

export interface CreateBookRequest {
  title: string;
  genre: string;
  platform: string;
  target_chapters: number;
  chapter_word_count: number;
}

export const booksApi = {
  list: () => api.get<Book[]>("/api/books"),
  get: (id: string) => api.get<Book>(`/api/books/${id}`),
  create: (data: CreateBookRequest) => api.post<Book>("/api/books", data),
  updateStatus: (id: string, status: string) => api.patch<Book>(`/api/books/${id}/status`, { status })
};
