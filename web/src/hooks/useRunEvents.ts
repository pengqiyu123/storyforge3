import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { resolveApiUrl } from "@/api/client";
import type { RunRecord, RunStatus, StageResult } from "@/api/runs";
import { chapterStatusKey } from "@/hooks/useChapters";
import { runRecordKey } from "@/hooks/useRunRecord";

const DEFAULT_TARGET_STAGES = ["plan", "draft", "audit", "revise", "approve", "truth", "export"];
const SSE_MAX_RETRIES = 5;
const SSE_BASE_DELAY_MS = 1000;

export interface RunEvent {
  type:
    | "run:start"
    | "run:complete"
    | "run:waiting"
    | "stage:start"
    | "stage:progress"
    | "stage:complete"
    | "stage:error"
    | "llm:chunk";
  run_id?: string;
  book_id: string;
  chapter_no: number;
  stage?: string;
  message?: string;
  detail?: Record<string, unknown> | null;
}

export function useRunEvents(bookId?: string, chapterNo?: number, onEvent?: (event: RunEvent) => void) {
  const queryClient = useQueryClient();
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  useEffect(() => {
    if (!bookId || !chapterNo || typeof EventSource === "undefined") {
      return undefined;
    }

    let source: EventSource | null = null;
    let retryCount = 0;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let cancelled = false;

    const scheduleReconnect = () => {
      if (cancelled || retryCount >= SSE_MAX_RETRIES) {
        return;
      }
      const delay = SSE_BASE_DELAY_MS * 2 ** retryCount;
      retryCount += 1;
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        if (!cancelled) {
          connect();
        }
      }, delay);
    };

    const connect = () => {
      const params = new URLSearchParams({ book_id: bookId, chapter_no: String(chapterNo) });
      const next = new EventSource(resolveApiUrl(`/api/events?${params.toString()}`));
      source = next;
      next.onmessage = (message) => {
        retryCount = 0;
        const event = JSON.parse(message.data) as RunEvent;
        if (event.book_id !== bookId || event.chapter_no !== chapterNo || !isRunViewerEvent(event.type)) {
          return;
        }
        onEventRef.current?.(event);
        applyRunEvent(queryClient, bookId, chapterNo, event);
      };
      next.onerror = () => {
        next.close();
        if (source === next) {
          source = null;
        }
        scheduleReconnect();
      };
    };

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      source?.close();
      source = null;
    };
  }, [bookId, chapterNo, queryClient]);
}

function applyRunEvent(
  queryClient: ReturnType<typeof useQueryClient>,
  bookId: string,
  chapterNo: number,
  event: RunEvent
) {
  queryClient.setQueryData<RunRecord | null>(runRecordKey(bookId, chapterNo), (previous) => reduceRunEvent(previous, event));
  queryClient.invalidateQueries({ queryKey: chapterStatusKey(bookId, chapterNo) });
  if (event.type === "run:complete" || event.type === "stage:error") {
    queryClient.invalidateQueries({ queryKey: runRecordKey(bookId, chapterNo) });
  }
}

function reduceRunEvent(previous: RunRecord | null | undefined, event: RunEvent): RunRecord {
  const now = new Date().toISOString();
  const record = previous ?? createEventRunRecord(event, now);
  const runId = event.run_id ?? record.run_id;
  const stage = event.stage ?? record.current_stage;
  const live = { ...(record.live ?? {}) };

  if (event.type === "run:start") {
    return {
      ...record,
      run_id: runId,
      mode: stringDetail(event.detail, "mode") || record.mode,
      target_stages: stringArrayDetail(event.detail, "target_stages") ?? record.target_stages,
      status: "running",
      updated_at: now,
      live: { stage: null, message: event.message || "run started", streamText: "" }
    };
  }

  if (event.type === "stage:start" && stage) {
    return {
      ...record,
      run_id: runId,
      status: "running",
      current_stage: stage,
      updated_at: now,
      resume_from: stage,
      stage_results: {
        ...record.stage_results,
        [stage]: {
          ...(record.stage_results[stage] ?? {}),
          stage,
          status: "running",
          started_at: record.stage_results[stage]?.started_at ?? now,
          finished_at: null,
          error_code: null,
          error_message: null
        }
      },
      live: { ...live, stage, message: event.message, progress: null, errorMessage: undefined }
    };
  }

  if (event.type === "stage:progress" && stage) {
    return {
      ...record,
      current_stage: stage,
      updated_at: now,
      live: {
        ...live,
        stage,
        message: event.message,
        progress: progressDetail(event.detail)
      }
    };
  }

  if (event.type === "llm:chunk") {
    const text = typeof event.detail?.text === "string" ? event.detail.text : "";
    const streamText = live.streamText ? `${live.streamText}\n\n${text}` : text;
    return {
      ...record,
      updated_at: now,
      live: { ...live, stage: stage ?? "draft", streamText }
    };
  }

  if (event.type === "stage:complete" && stage) {
    const stageResult = completeStage(record.stage_results[stage], stage, now, event.detail ?? null);
    return {
      ...record,
      current_stage: record.current_stage === stage ? null : record.current_stage,
      updated_at: now,
      resume_from: null,
      stage_results: { ...record.stage_results, [stage]: stageResult },
      live: { ...live, stage, message: event.message }
    };
  }

  if (event.type === "run:waiting") {
    return {
      ...record,
      status: "waiting_for_human",
      current_stage: stage,
      updated_at: now,
      live: { ...live, stage, waitingMessage: event.message || "等待作者确认" }
    };
  }

  if (event.type === "stage:error" && stage) {
    return {
      ...record,
      status: "failed",
      current_stage: stage,
      updated_at: now,
      error_message: event.message || "运行失败",
      resume_from: stage,
      stage_results: {
        ...record.stage_results,
        [stage]: failStage(record.stage_results[stage], stage, now, event.message || "运行失败")
      },
      live: { ...live, stage, errorMessage: event.message || "运行失败" }
    };
  }

  if (event.type === "run:complete") {
    return {
      ...record,
      status: finalRunStatus(event.detail),
      current_stage: null,
      updated_at: now,
      error_message: finalRunStatus(event.detail) === "failed" ? stringDetail(event.detail, "error_message") || record.error_message : null,
      resume_from: null,
      live: { ...live, message: event.message || "run complete" }
    };
  }

  return { ...record, updated_at: now };
}

function createEventRunRecord(event: RunEvent, now: string): RunRecord {
  return {
    run_id: event.run_id ?? "",
    book_id: event.book_id,
    chapter_no: event.chapter_no,
    mode: stringDetail(event.detail, "mode") || "full",
    target_stages: stringArrayDetail(event.detail, "target_stages") ?? DEFAULT_TARGET_STAGES,
    status: "pending",
    current_stage: null,
    started_at: now,
    updated_at: now,
    stage_results: {},
    llm_calls: [],
    error_code: null,
    error_message: null,
    resume_from: null
  };
}

function completeStage(previous: StageResult | undefined, stage: string, now: string, summary: Record<string, unknown> | null): StageResult {
  return {
    ...(previous ?? {}),
    stage,
    status: "completed",
    started_at: previous?.started_at ?? now,
    finished_at: now,
    error_code: null,
    error_message: null,
    summary
  };
}

function failStage(previous: StageResult | undefined, stage: string, now: string, message: string): StageResult {
  return {
    ...(previous ?? {}),
    stage,
    status: "failed",
    started_at: previous?.started_at ?? now,
    finished_at: now,
    error_message: message
  };
}

function isRunViewerEvent(type: string): type is RunEvent["type"] {
  return (
    type === "run:start" ||
    type === "run:complete" ||
    type === "run:waiting" ||
    type === "stage:start" ||
    type === "stage:progress" ||
    type === "stage:complete" ||
    type === "stage:error" ||
    type === "llm:chunk"
  );
}

function progressDetail(detail: Record<string, unknown> | null | undefined) {
  if (!detail) {
    return null;
  }
  return {
    completed: Number(detail.completed) || 0,
    total: Number(detail.total) || 0
  };
}

function stringArrayDetail(detail: Record<string, unknown> | null | undefined, key: string): string[] | null {
  const value = detail?.[key];
  if (!Array.isArray(value)) {
    return null;
  }
  return value.map((item) => String(item));
}

function stringDetail(detail: Record<string, unknown> | null | undefined, key: string): string {
  const value = detail?.[key];
  return typeof value === "string" ? value : "";
}

function finalRunStatus(detail: Record<string, unknown> | null | undefined): RunStatus {
  const raw = stringDetail(detail, "final_status") || stringDetail(detail, "status") || "completed";
  return isRunStatus(raw) ? raw : "completed";
}

function isRunStatus(value: string): value is RunStatus {
  return ["pending", "running", "waiting_for_human", "completed", "failed", "resumable", "cancelled"].includes(value);
}
