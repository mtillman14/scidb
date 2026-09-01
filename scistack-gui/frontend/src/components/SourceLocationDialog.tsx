/**
 * SourceLocationDialog — shows "<name> is defined at: <file>:<line>".
 *
 * This used to be a `window.alert`, whose text the OS/webview renders as a
 * non-selectable label: the whole point of the message is the path, and there
 * was no way to get it out of the dialog except by retyping it. Same message,
 * rendered in-app, in a read-only <input> that is focused and pre-selected on
 * open (so Ctrl/Cmd-C just works) with an explicit Copy button as a fallback.
 *
 * Rendered through a portal to document.body: FunctionNode lives inside the
 * React Flow viewport, which carries a CSS transform — a `position: fixed`
 * overlay mounted there would be positioned against the transformed pane and
 * pan/zoom with the canvas instead of covering the window.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { createPortal } from "react-dom";
import * as modalStyles from "./modalStyles";

export interface SourceLocation {
  name: string;
  file: string;
  line: number;
}

export function SourceLocationDialog({
  location,
  onClose,
}: {
  location: SourceLocation;
  onClose: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [copied, setCopied] = useState(false);
  const text = `${location.file}:${location.line}`;

  // Focus + select on open so the path is one Ctrl/Cmd-C away.
  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);

  const handleCopy = useCallback(async () => {
    inputRef.current?.select();
    try {
      // navigator.clipboard is unavailable in some webviews (and on
      // non-secure origins); fall back to the legacy selection-based copy,
      // which is why the text lives in a real <input> rather than a <span>.
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        document.execCommand("copy");
      }
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn("copy of source location failed:", err);
    }
  }, [text]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    },
    [onClose],
  );

  return createPortal(
    // Clicks/drags are stopped here: the dialog is a child of a React Flow
    // node in the FunctionNode case, and unstopped events would select or
    // drag the node underneath it.
    <div
      style={modalStyles.overlay}
      role="dialog"
      aria-modal="true"
      onClick={onClose}
      onMouseDown={(e) => e.stopPropagation()}
      onKeyDown={handleKeyDown}
    >
      <div
        style={{ ...modalStyles.dialog, width: 560, maxWidth: "90vw" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={modalStyles.dialogTitle}>
          <span style={styles.fnName}>{location.name}</span> is defined at:
        </div>
        <div style={styles.row}>
          <input
            ref={inputRef}
            style={styles.pathInput}
            value={text}
            readOnly
            spellCheck={false}
            onFocus={(e) => e.target.select()}
          />
          <button type="button" style={styles.button} onClick={handleCopy}>
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
        <div style={styles.footer}>
          <button type="button" style={styles.button} onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

const styles: Record<string, CSSProperties> = {
  fnName: {
    fontFamily: "monospace",
  },
  row: {
    display: "flex",
    gap: 8,
    alignItems: "center",
  },
  pathInput: {
    flex: 1,
    background: "#0f0f1e",
    color: "#eee",
    border: "1px solid #2a2a4a",
    borderRadius: 4,
    padding: "6px 8px",
    fontFamily: "monospace",
    fontSize: 13,
    // The path is the payload — let the user drag-select any part of it.
    userSelect: "text",
  },
  button: {
    padding: "6px 12px",
    background: "#2a2a4a",
    color: "#eee",
    border: "1px solid #3a3a5a",
    borderRadius: 4,
    cursor: "pointer",
    fontSize: 12,
  },
  footer: {
    display: "flex",
    justifyContent: "flex-end",
    marginTop: 12,
  },
};
