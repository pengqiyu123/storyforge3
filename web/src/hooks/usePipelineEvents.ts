import { useEffect } from "react";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { resolveApiUrl } from "@/api/client";
import { chapterStatusKey } from "@/hooks/useChapters";

export interface PipelineEvent {
  type: "pipeline:start" | "pipeline:complete" | "pipeline:error";
  book_id: string;
  chapter_no: number;
  stage?: string;
  message?: string;
  detail?: Record<string, unknown> | null;
}

export function usePipelineEvents(bookId?: string, chapterNo?: number, onEvent?: (event: PipelineEvent) => void) {
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!bookId || !chapterNo || typeof EventSource === "undefined") {
      return undefined;
    }
    const params = new URLSearchParams({ book_id: bookId, chapter_no: String(chapterNo) });
    const source = new EventSource(resolveApiUrl(`/api/events?${params.toString()}`));
    source.onmessage = (message) => {
      const event = JSON.parse(message.data) as PipelineEvent;
      onEvent?.(event);
      queryClient.invalidateQueries({ queryKey: chapterStatusKey(bookId, chapterNo) });
      if (event.type === "pipeline:error") {
        toast.error(event.message || "管线运行失败");
      } else if (event.type === "pipeline:complete") {
        toast.success(event.message || `${event.stage ?? "管线"}完成`);
      } else {
        toast.info(event.message || `${event.stage ?? "管线"}已启动`);
      }
    };
    source.onerror = () => {
      source.close();
    };
    return () => source.close();
  }, [bookId, chapterNo, onEvent, queryClient]);
}
