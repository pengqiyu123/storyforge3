import { api } from "./client";

export type ChapterStatus =
  | "empty"
  | "planned"
  | "drafted"
  | "settled"
  | "audited"
  | "needs_revision"
  | "revised"
  | "approved"
  | "truth_committed"
  | "exported"
  | "needs_review";

export interface ChapterResult {
  book_id: string;
  chapter_no: number;
  status: ChapterStatus | string;
  title: string;
  text?: string;
  content_hash?: string | null;
  actual_chars?: number;
  revision_diff?: RevisionDiff | null;
  audit_result?: AuditResult | null;
  error?: string | null;
}

export interface ChapterIntent {
  chapter_no: number;
  goal: string;
  outline_node: string;
  arc_context: string;
  must_keep: string[];
  must_avoid: string[];
  style_emphasis: string[];
}

export interface AuditResult {
  chapter_no: number;
  passed: boolean;
  blocking_issues: string[];
  warnings: string[];
  info: string[];
  rule_results?: RuleResult[];
}

export interface RuleResult {
  rule_id: string;
  passed: boolean;
  severity: "INFO" | "WARNING" | "BLOCKING";
  category: "INTEGRITY" | "AI_TELL" | "STYLE" | "STRUCTURE" | "META";
  message: string;
  detail: Record<string, unknown>;
}

export interface ChapterTextResponse {
  text: string;
}

export interface LlmAuditIssue {
  severity: string;
  dimension: string;
  description: string;
  suggestion: string;
}

export interface LlmAuditResult {
  passed: boolean;
  issues: LlmAuditIssue[];
}

export interface NormalizeRequest {
  text: string;
  target_chars: number;
  soft_ratio?: number;
}

export interface NormalizeResult {
  text: string;
  action: string;
  original_chars: number;
  final_chars: number;
}

export interface UpdateTextRequest {
  text: string;
  expected_hash?: string;
}

export interface RevisionDiffBlock {
  kind: "replace" | "insert" | "delete";
  before_text: string;
  after_text: string;
}

export interface RevisionDiffSummary {
  changed_blocks: number;
  added_blocks: number;
  removed_blocks: number;
  before_chars: number;
  after_chars: number;
}

export interface RevisionDiff {
  unit: "paragraph" | string;
  summary: RevisionDiffSummary;
  blocks: RevisionDiffBlock[];
}

export interface ExportPreview {
  chapter_no: number;
  format: string;
  preview_text: string;
  char_count: number;
  format_errors: string[];
}

export const chaptersApi = {
  getStatus: (bookId: string, chapterNo: number) => api.get<ChapterResult>(`/api/books/${bookId}/chapters/${chapterNo}/status`),
  getPlan: (bookId: string, chapterNo: number) => api.get<ChapterIntent>(`/api/books/${bookId}/chapters/${chapterNo}/plan`),
  plan: (bookId: string, chapterNo: number) => api.post<ChapterIntent>(`/api/books/${bookId}/chapters/${chapterNo}/plan`, {}),
  rePlan: (bookId: string, chapterNo: number) => api.post<ChapterIntent>(`/api/books/${bookId}/chapters/${chapterNo}/re-plan`, {}),
  draft: (bookId: string, chapterNo: number) => api.post<ChapterTextResponse>(`/api/books/${bookId}/chapters/${chapterNo}/draft`, {}),
  audit: (bookId: string, chapterNo: number) => api.post<AuditResult>(`/api/books/${bookId}/chapters/${chapterNo}/audit`, {}),
  reAudit: (bookId: string, chapterNo: number) => api.post<AuditResult>(`/api/books/${bookId}/chapters/${chapterNo}/re-audit`, {}),
  llmAudit: (bookId: string, chapterNo: number, text: string) =>
    api.post<LlmAuditResult>(`/api/books/${bookId}/chapters/${chapterNo}/llm-audit`, { text }),
  normalize: (bookId: string, chapterNo: number, data: NormalizeRequest) =>
    api.post<NormalizeResult>(`/api/books/${bookId}/chapters/${chapterNo}/normalize`, data),
  revise: (bookId: string, chapterNo: number, mode = "auto") =>
    api.post<ChapterResult>(`/api/books/${bookId}/chapters/${chapterNo}/revise`, { mode }),
  updateText: (bookId: string, chapterNo: number, data: UpdateTextRequest) =>
    api.put<ChapterResult>(`/api/books/${bookId}/chapters/${chapterNo}/text`, data),
  approve: (bookId: string, chapterNo: number) => api.post<ChapterResult>(`/api/books/${bookId}/chapters/${chapterNo}/approve`, {}),
  exportChapter: (bookId: string, chapterNo: number, fmt = "tomato_txt") =>
    api.post<{ path: string }>(`/api/books/${bookId}/chapters/${chapterNo}/export`, { fmt }),
  unexport: (bookId: string, chapterNo: number) => api.post<ChapterResult>(`/api/books/${bookId}/chapters/${chapterNo}/unexport`, {}),
  exportPreview: (bookId: string, chapterNo: number, fmt = "tomato_txt") =>
    api.get<ExportPreview>(`/api/books/${bookId}/chapters/${chapterNo}/export-preview?fmt=${fmt}`),
  runFullPipeline: (bookId: string, chapterNo: number) => api.post<ChapterResult>(`/api/books/${bookId}/chapters/${chapterNo}/run`, {})
};
