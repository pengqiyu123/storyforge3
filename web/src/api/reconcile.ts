import { api } from "./client";

export type ChapterConsistencyStatus = "consistent" | "inconsistent" | string;
export type ChapterValidity = "valid" | "partial" | "orphan" | "empty" | string;

export interface ChapterConsistency {
  chapter_no: number;
  has_text: boolean;
  has_plan: boolean;
  has_truth: boolean;
  has_export: boolean;
  has_state: boolean;
  has_run: boolean;
  state_status: string | null;
  status: ChapterConsistencyStatus;
  validity: ChapterValidity;
  inconsistent_reasons: string[];
}

export interface BookReconciliation {
  book_id: string;
  chapters: ChapterConsistency[];
  inconsistent_count: number;
  max_chapter: number;
  valid_chapter_count: number;
  highest_contiguous_chapter: number;
  next_writable_chapter_no: number;
  has_blocking_inconsistency: boolean;
}

const reasonLabels: Record<string, string> = {
  export_without_state: "已导出但无状态记录",
  export_without_text: "已导出但无正文文件",
  truth_without_state: "有 Truth 但无状态记录",
  orphan_state: "状态记录已完成但缺少正文"
};

export function inconsistentReasonLabel(reason: string): string {
  return reasonLabels[reason] ?? reason;
}

export const reconcileApi = {
  get: (bookId: string) => api.get<BookReconciliation>(`/api/books/${bookId}/reconcile`)
};
