import { useEffect, useRef } from "react";
import { EditorState, StateEffect, StateField } from "@codemirror/state";
import { markdown } from "@codemirror/lang-markdown";
import { oneDark } from "@codemirror/theme-one-dark";
import { Decoration, type DecorationSet, placeholder as placeholderExt } from "@codemirror/view";
import { EditorView, basicSetup } from "codemirror";
import { cn, countChineseChars } from "@/lib/utils";

export interface HighlightRange {
  from: number;
  to: number;
  severity: "BLOCKING" | "WARNING";
}

interface ChapterEditorProps {
  value: string;
  onChange?: (value: string) => void;
  readOnly?: boolean;
  placeholder?: string;
  className?: string;
  highlights?: HighlightRange[];
  scrollToOffset?: number;
}

const setAuditHighlights = StateEffect.define<DecorationSet>();

const auditHighlightField = StateField.define<DecorationSet>({
  create: () => Decoration.none,
  update(decorations, transaction) {
    for (const effect of transaction.effects) {
      if (effect.is(setAuditHighlights)) {
        return effect.value;
      }
    }
    return transaction.docChanged ? decorations.map(transaction.changes) : decorations;
  },
  provide: (field) => EditorView.decorations.from(field)
});

export function ChapterEditor({
  value,
  onChange,
  readOnly = false,
  placeholder: placeholderText = "",
  className = "",
  highlights = [],
  scrollToOffset
}: ChapterEditorProps) {
  const editorRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);

  useEffect(() => {
    if (!editorRef.current) return;

    const baseTheme = EditorView.baseTheme({
      "&": {
        height: "100%",
        minHeight: "100%"
      },
      ".cm-scroller": {
        overflow: "auto",
        fontFamily: '"Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif',
        fontSize: "14px",
        lineHeight: "1.75"
      },
      "&light .cm-content, &dark .cm-content": {
        padding: "12px 0 32px"
      },
      "&light .cm-editor, &dark .cm-editor": {
        backgroundColor: "transparent"
      },
      "&.cm-focused": {
        outline: "none"
      },
      ".cm-gutters": {
        backgroundColor: "rgba(9, 9, 11, 0.54)",
        borderRight: "1px solid rgba(39, 39, 42, 0.9)"
      },
      ".cm-audit-blocking": {
        backgroundColor: "rgba(239, 68, 68, 0.15)",
        borderBottom: "2px solid #ef4444"
      },
      ".cm-audit-warning": {
        backgroundColor: "rgba(245, 158, 11, 0.15)",
        borderBottom: "2px solid #f59e0b"
      }
    });

    const extensions = [
      basicSetup,
      markdown(),
      baseTheme,
      auditHighlightField,
      EditorView.lineWrapping,
      EditorState.readOnly.of(readOnly)
    ];

    if (!readOnly) {
      extensions.push(
        placeholderExt(placeholderText),
        EditorView.updateListener.of((update) => {
          if (update.docChanged && onChange) {
            onChange(update.state.doc.toString());
          }
        })
      );
    } else {
      extensions.push(
        EditorView.theme({
          ".cm-cursor, .cm-dropCursor": { border: "none" },
          ".cm-activeLine": { backgroundColor: "transparent !important" },
          ".cm-activeLineGutter": { backgroundColor: "transparent !important" }
        })
      );
    }

    extensions.push(oneDark);

    const state = EditorState.create({
      doc: value,
      extensions
    });

    const view = new EditorView({
      state,
      parent: editorRef.current
    });

    viewRef.current = view;

    return () => {
      view.destroy();
      viewRef.current = null;
    };
  }, [onChange, placeholderText, readOnly]);

  useEffect(() => {
    if (viewRef.current && viewRef.current.state.doc.toString() !== value) {
      const transaction = viewRef.current.state.update({
        changes: {
          from: 0,
          to: viewRef.current.state.doc.length,
          insert: value
        }
      });
      viewRef.current.dispatch(transaction);
    }
  }, [value]);

  useEffect(() => {
    if (!viewRef.current) {
      return;
    }
    viewRef.current.dispatch({
      effects: setAuditHighlights.of(buildDecorations(viewRef.current, highlights))
    });
  }, [highlights]);

  useEffect(() => {
    if (scrollToOffset === undefined || !viewRef.current) {
      return;
    }
    const position = Math.max(0, Math.min(scrollToOffset, viewRef.current.state.doc.length));
    viewRef.current.dispatch({
      effects: EditorView.scrollIntoView(position, { y: "center" })
    });
  }, [scrollToOffset]);

  return (
    <div className={cn("relative h-full min-h-52 overflow-hidden rounded-md border border-zinc-800 bg-black/30", className)}>
      <div ref={editorRef} aria-label="章节文本预览" className="h-full" />
      <span className="pointer-events-none absolute bottom-2 right-3 rounded border border-zinc-800 bg-zinc-950/90 px-2 py-0.5 text-xs text-zinc-500">
        {countChineseChars(value)} 字
      </span>
    </div>
  );
}

function buildDecorations(view: EditorView, ranges: HighlightRange[]): DecorationSet {
  const docLength = view.state.doc.length;
  const marks = ranges
    .map((range) => {
      const from = Math.max(0, Math.min(range.from, docLength));
      const to = Math.max(from, Math.min(range.to, docLength));
      if (from === to) {
        return null;
      }
      return Decoration.mark({
        class: range.severity === "BLOCKING" ? "cm-audit-blocking" : "cm-audit-warning"
      }).range(from, to);
    })
    .filter((mark): mark is NonNullable<typeof mark> => mark !== null);
  return Decoration.set(marks, true);
}
