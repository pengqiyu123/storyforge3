import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ChapterEditor } from "./ChapterEditor";

interface MockExtension {
  type?: string;
  value?: unknown;
  callback?: (update: { docChanged: boolean; state: { doc: { toString: () => string } } }) => void;
}

const codeMirrorMocks = vi.hoisted(() => {
  const dispatches: unknown[] = [];

  class MockDoc {
    constructor(private value: string) {}

    toString() {
      return this.value;
    }

    get length() {
      return this.value.length;
    }
  }

  class MockEditorState {
    doc: MockDoc;
    extensions: MockExtension[];

    constructor(doc: string, extensions: MockExtension[]) {
      this.doc = new MockDoc(doc);
      this.extensions = extensions;
    }

    update({ changes }: { changes: { insert: string } }) {
      return { value: changes.insert, fromExternal: true };
    }

    static create({ doc, extensions }: { doc: string; extensions: MockExtension[] }) {
      return new MockEditorState(doc, extensions);
    }

    static readOnly = {
      of: (value: boolean): MockExtension => ({ type: "readOnly", value })
    };
  }

  const MockStateEffect = {
    define: () => {
      const effectType = {
        of: (value: unknown) => ({
          type: "effect",
          value,
          is: (other: unknown) => other === effectType
        })
      };
      return effectType;
    }
  };

  const MockStateField = {
    define: (spec: unknown): MockExtension => ({ type: "stateField", value: spec })
  };

  const MockDecoration = {
    none: { type: "decorations", ranges: [] },
    mark: ({ class: className }: { class: string }) => ({
      range: (from: number, to: number) => ({ type: "range", from, to, className })
    }),
    set: (ranges: unknown[]) => ({ type: "decorations", ranges })
  };

  class MockEditorView {
    state: MockEditorState;
    parent: Element;
    root: HTMLDivElement;
    listener?: MockExtension["callback"];

    constructor({ state, parent }: { state: MockEditorState; parent: Element }) {
      this.state = state;
      this.parent = parent;
      this.listener = state.extensions.find((item) => item.type === "listener")?.callback;
      this.root = document.createElement("div");
      this.root.className = "cm-editor";
      this.root.setAttribute("role", "textbox");
      this.root.textContent = state.doc.toString();
      this.root.setAttribute("contenteditable", state.extensions.some((item) => item.type === "readOnly" && item.value) ? "false" : "true");

      const cursor = document.createElement("span");
      cursor.className = "cm-cursor";
      if (this.root.getAttribute("contenteditable") === "false") {
        cursor.setAttribute("data-hidden", "true");
      }
      this.root.appendChild(cursor);
      this.renderAuditMarks(state.extensions);

      this.root.addEventListener("input", () => {
        this.state.doc = new MockDoc(this.root.textContent ?? "");
        this.listener?.({ docChanged: true, state: this.state });
      });

      parent.appendChild(this.root);
    }

    dispatch(transaction: { value?: string; effects?: unknown }) {
      dispatches.push(transaction);
      if (typeof transaction.value === "string") {
        this.state.doc = new MockDoc(transaction.value);
        this.root.textContent = transaction.value;
      }
      if (transaction.effects) {
        const effects = Array.isArray(transaction.effects) ? transaction.effects : [transaction.effects];
        if (JSON.stringify(effects).includes("cm-audit-")) {
          this.renderAuditMarks(effects);
        }
      }
    }

    destroy() {
      this.root.remove();
    }

    static baseTheme = (value: unknown) => ({ type: "baseTheme", value });
    static lineWrapping = { type: "lineWrapping" };
    static updateListener = {
      of: (callback: MockExtension["callback"]): MockExtension => ({ type: "listener", callback })
    };
    static theme = (value: unknown) => ({ type: "theme", value });
    static decorations = {
      from: (field: unknown) => ({ type: "decorationsFrom", value: field })
    };
    static scrollIntoView = (position: number, options: unknown) => ({ type: "scrollIntoView", position, options });

    private renderAuditMarks(items: unknown[]) {
      this.root.querySelectorAll(".cm-audit-blocking, .cm-audit-warning").forEach((node) => node.remove());
      const serialized = JSON.stringify(items);
      if (serialized.includes("cm-audit-blocking")) {
        const mark = document.createElement("span");
        mark.className = "cm-audit-blocking";
        this.root.appendChild(mark);
      }
      if (serialized.includes("cm-audit-warning")) {
        const mark = document.createElement("span");
        mark.className = "cm-audit-warning";
        this.root.appendChild(mark);
      }
    }
  }

  return { dispatches, MockDecoration, MockEditorState, MockEditorView, MockStateEffect, MockStateField };
});

vi.mock("codemirror", () => ({
  EditorView: codeMirrorMocks.MockEditorView,
  basicSetup: { type: "basicSetup" }
}));

vi.mock("@codemirror/state", () => ({
  EditorState: codeMirrorMocks.MockEditorState,
  StateEffect: codeMirrorMocks.MockStateEffect,
  StateField: codeMirrorMocks.MockStateField
}));

vi.mock("@codemirror/lang-markdown", () => ({
  markdown: () => ({ type: "markdown" })
}));

vi.mock("@codemirror/theme-one-dark", () => ({
  oneDark: { type: "oneDark" }
}));

vi.mock("@codemirror/view", () => ({
  Decoration: codeMirrorMocks.MockDecoration,
  placeholder: (value: string) => ({ type: "placeholder", value })
}));

describe("ChapterEditor", () => {
  it("renders with value", () => {
    render(<ChapterEditor value="林默推开门。" />);

    expect(screen.getByRole("textbox")).toHaveTextContent("林默推开门。");
  });

  it("renders in readOnly mode", () => {
    render(<ChapterEditor value="林默推开门。" readOnly />);

    expect(screen.getByRole("textbox")).toHaveAttribute("contenteditable", "false");
    expect(document.querySelector(".cm-cursor")).toHaveAttribute("data-hidden", "true");
  });

  it("calls onChange when editing", () => {
    const onChange = vi.fn();
    render(<ChapterEditor value="林默推开门。" onChange={onChange} />);

    const editor = screen.getByRole("textbox");
    editor.textContent = "林默推开门。声音停了。";
    fireEvent.input(editor);

    expect(onChange).toHaveBeenCalledWith("林默推开门。声音停了。");
  });

  it("syncs external value", () => {
    const { rerender } = render(<ChapterEditor value="旧稿" />);

    rerender(<ChapterEditor value="新稿" />);

    expect(screen.getByRole("textbox")).toHaveTextContent("新稿");
  });

  it("displays chinese char count", () => {
    render(<ChapterEditor value="林默推开门。A1" />);

    expect(screen.getByText("5 字")).toBeInTheDocument();
  });

  it("renders audit highlights and scrolls to the requested offset", async () => {
    codeMirrorMocks.dispatches.length = 0;

    render(
      <ChapterEditor
        value={"第一段。\n\n第二段。"}
        highlights={[{ from: 0, to: 4, severity: "BLOCKING" }]}
        scrollToOffset={0}
      />
    );

    await waitFor(() => expect(document.querySelector(".cm-audit-blocking")).toBeInTheDocument());
    expect(JSON.stringify(codeMirrorMocks.dispatches)).toContain("scrollIntoView");
  });
});
