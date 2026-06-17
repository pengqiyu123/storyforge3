import { useEffect, useState, useCallback } from "react";
import { resolveApiUrl } from "@/api/client";

/**
 * Global SSE subscription for the dashboard live-run panel.
 *
 * Unlike useRunEvents (per-chapter), this subscribes to ALL pipeline events
 * via GET /api/events with no filter. It tracks active runs and exposes:
 *  - activeRuns: chapters currently being processed (stage started, not yet completed/errored)
 *  - streamText: accumulated LLM chunk text for the most recently active chapter
 */

export type StageStatus = "pending" | "running" | "completed" | "failed";

export interface LiveStageState {
  stage: string;
  status: StageStatus;
}

export interface LiveRunState {
  bookId: string;
  bookTitle: string;
  chapterNo: number;
  currentStage: string | null;
  stageStatuses: Record<string, StageStatus>;
  streamText: string;
  message: string | null;
  errorMessage: string | null;
  startedAt: number;
  updatedAt: number;
}

interface PipelineEventPayload {
  type: string;
  run_id?: string;
  book_id: string;
  chapter_no: number;
  stage?: string | null;
  message?: string | null;
  detail?: Record<string, unknown> | null;
}

const SSE_MAX_RETRIES = 5;
const SSE_BASE_DELAY_MS = 1000;
const PIPELINE_STAGES = ["plan", "draft", "audit", "revise", "approve", "truth", "export"];
const TERMINAL_EVENT_TYPES = new Set(["pipeline:complete", "pipeline:error", "stage:complete", "stage:error", "run:complete"]);

function runKey(bookId: string, chapterNo: number): string {
  return `${bookId}:${chapterNo}`;
}

function emptyStageStatuses(): Record<string, StageStatus> {
  const map: Record<string, StageStatus> = {};
  for (const stage of PIPELINE_STAGES) {
    map[stage] = "pending";
  }
  return map;
}

function reduceEvent(
  runs: Map<string, LiveRunState>,
  event: PipelineEventPayload
): Map<string, LiveRunState> {
  const key = runKey(event.book_id, event.chapter_no);
  const now = Date.now();
  const existing = runs.get(key);
  const stage = event.stage ?? existing?.currentStage ?? null;

  // Determine book title from detail or fallback to book_id slug
  const bookTitle = (event.detail?.book_title as string) ?? existing?.bookTitle ?? event.book_id;

  function getOrCreate(): LiveRunState {
    if (existing) {
      return existing;
    }
    return {
      bookId: event.book_id,
      bookTitle,
      chapterNo: event.chapter_no,
      currentStage: null,
      stageStatuses: emptyStageStatuses(),
      streamText: "",
      message: null,
      errorMessage: null,
      startedAt: now,
      updatedAt: now,
    };
  }

  const next = new Map(runs);

  if (event.type === "pipeline:start" || event.type === "stage:start") {
    const run = getOrCreate();
    if (stage) {
      run.stageStatuses[stage] = "running";
      run.currentStage = stage;
    }
    run.message = event.message ?? run.message;
    run.updatedAt = now;
    next.set(key, run);
    return next;
  }

  if (event.type === "stage:progress" || event.type === "pipeline:progress") {
    const run = getOrCreate();
    if (stage) {
      run.currentStage = stage;
    }
    run.message = event.message ?? run.message;
    run.updatedAt = now;
    next.set(key, run);
    return next;
  }

  if (event.type === "llm:chunk") {
    const run = getOrCreate();
    const text = typeof event.detail?.text === "string" ? event.detail.text : "";
    run.streamText = run.streamText ? `${run.streamText}\n\n${text}` : text;
    run.updatedAt = now;
    next.set(key, run);
    return next;
  }

  if (event.type === "stage:complete" || event.type === "pipeline:complete") {
    const run = getOrCreate();
    if (stage) {
      run.stageStatuses[stage] = "completed";
    }
    // pipeline:complete without a specific stage means the whole thing finished
    if (event.type === "pipeline:complete") {
      run.currentStage = null;
    } else if (run.currentStage === stage) {
      run.currentStage = null;
    }
    run.message = event.message ?? run.message;
    run.updatedAt = now;
    next.set(key, run);
    return next;
  }

  if (event.type === "stage:error" || event.type === "pipeline:error" || event.type === "run:complete") {
    const run = getOrCreate();
    if (event.type === "stage:error" && stage) {
      run.stageStatuses[stage] = "failed";
    }
    run.errorMessage = event.message ?? run.errorMessage;
    run.currentStage = null;
    run.updatedAt = now;
    next.set(key, run);
    return next;
  }

  return runs;
}

export interface UseGlobalRunEventsResult {
  /** Chapters currently being processed or recently completed (last 30s). */
  activeRuns: LiveRunState[];
}

export function useGlobalRunEvents(): UseGlobalRunEventsResult {
  const [runs, setRuns] = useState<Map<string, LiveRunState>>(new Map());

  const handleEvent = useCallback((event: PipelineEventPayload) => {
    setRuns((prev) => reduceEvent(prev, event));
  }, []);

  useEffect(() => {
    if (typeof EventSource === "undefined") {
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
      const next = new EventSource(resolveApiUrl("/api/events"));
      source = next;
      next.onmessage = (message) => {
        retryCount = 0;
        try {
          const event = JSON.parse(message.data) as PipelineEventPayload;
          handleEvent(event);
        } catch {
          // Ignore malformed events
        }
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
  }, [handleEvent]);

  // Prune runs that have been terminal for more than 30 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      setRuns((prev) => {
        if (prev.size === 0) {
          return prev;
        }
        const now = Date.now();
        const PRUNE_MS = 30_000;
        let changed = false;
        const next = new Map<string, LiveRunState>();
        for (const [key, run] of prev) {
          const isTerminal = run.currentStage === null && !run.errorMessage;
          if (isTerminal && now - run.updatedAt > PRUNE_MS) {
            changed = true;
            continue;
          }
          next.set(key, run);
        }
        return changed ? next : prev;
      });
    }, 10_000);
    return () => clearInterval(interval);
  }, []);

  const activeRuns = Array.from(runs.values()).sort((a, b) => b.startedAt - a.startedAt);

  return { activeRuns };
}
