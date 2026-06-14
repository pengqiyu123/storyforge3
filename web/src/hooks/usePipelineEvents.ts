import { useEffect, useRef } from "react";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { resolveApiUrl } from "@/api/client";
import { chapterStatusKey } from "@/hooks/useChapters";

export interface PipelineEvent {
  type:
    | "pipeline:start"
    | "pipeline:progress"
    | "pipeline:complete"
    | "pipeline:error"
    | "audit:complete"
    | "llm:chunk"
    | "llm:progress";
  book_id: string;
  chapter_no: number;
  stage?: string;
  message?: string;
  detail?: Record<string, unknown> | null;
}

export function usePipelineEvents(bookId?: string, chapterNo?: number, onEvent?: (event: PipelineEvent) => void) {
  const queryClient = useQueryClient();
  // Keep the latest callback in a ref so the EventSource subscription is NOT torn down
  // and rebuilt on every render (the inline onEvent closure changes each render, which
  // previously caused SSE events — pipeline:start / llm:progress — to be dropped).
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  useEffect(() => {
    if (!bookId || !chapterNo || typeof EventSource === "undefined") {
      return undefined;
    }
    const params = new URLSearchParams({ book_id: bookId, chapter_no: String(chapterNo) });
    const source = new EventSource(resolveApiUrl(`/api/events?${params.toString()}`));
    source.onmessage = (message) => {
      const event = JSON.parse(message.data) as PipelineEvent;
      onEventRef.current?.(event);
      queryClient.invalidateQueries({ queryKey: chapterStatusKey(bookId, chapterNo) });
      if (event.type === "pipeline:error") {
        toast.error(classifyPipelineErrorMessage(event));
      } else if (event.type === "pipeline:complete") {
        toast.success(event.message || `${event.stage ?? "管线"}完成`);
      } else if (event.type === "pipeline:start") {
        toast.info(event.message || `${event.stage ?? "管线"}已启动`);
      }
    };
    source.onerror = () => {
      source.close();
    };
    return () => source.close();
  }, [bookId, chapterNo, queryClient]);
}

function classifyPipelineErrorMessage(event: PipelineEvent): string {
  const message = event.message || "管线运行失败";
  if (message.includes("timed out") || message.includes("超时")) {
    return "章节起草超时，请检查网络连接";
  }
  if (message.includes("rate limit") || message.includes("限流") || message.includes("429")) {
    return "Provider 限流，请稍后重试";
  }
  return message;
}
