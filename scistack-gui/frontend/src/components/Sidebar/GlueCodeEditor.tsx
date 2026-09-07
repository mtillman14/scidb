/**
 * GlueCodeEditor — the code surface for a glue node's body.
 *
 * Deliberately a self-contained editor rather than Monaco *for now*. Monaco is
 * the intended end state (it is a web component, so it highlights a buffer in
 * both the browser build and the VS Code webview without the file needing to
 * be open in an editor tab), but it is a multi-megabyte dependency with worker
 * plumbing and CSP implications that cannot be verified from here. This
 * component is the seam: it owns the whole editing surface, so swapping in
 * `@monaco-editor/react` is a change to this file and nothing else.
 *
 * What it does provide, because a code box without them is actively annoying:
 * a monospace buffer, Tab inserting four spaces instead of moving focus, and
 * a gutter of line numbers that scrolls with the text.
 */

import { useCallback, useMemo, useRef } from 'react'

interface Props {
  value: string
  onChange: (next: string) => void
  onBlur?: () => void
  readOnly?: boolean
  /** 'python' | 'matlab' — reserved for the Monaco swap's language id. */
  language?: string
  rows?: number
}

const INDENT = '    '

export default function GlueCodeEditor({
  value,
  onChange,
  onBlur,
  readOnly = false,
  rows = 14,
}: Props) {
  const textRef = useRef<HTMLTextAreaElement>(null)
  const gutterRef = useRef<HTMLDivElement>(null)

  const lineCount = useMemo(() => Math.max(value.split('\n').length, rows), [value, rows])

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key !== 'Tab' || readOnly) return
    // A code box that moves focus on Tab is unusable for indented code.
    e.preventDefault()
    const el = e.currentTarget
    const { selectionStart, selectionEnd } = el
    const next = value.slice(0, selectionStart) + INDENT + value.slice(selectionEnd)
    onChange(next)
    requestAnimationFrame(() => {
      el.selectionStart = el.selectionEnd = selectionStart + INDENT.length
    })
  }, [value, onChange, readOnly])

  const syncScroll = useCallback(() => {
    if (gutterRef.current && textRef.current) {
      gutterRef.current.scrollTop = textRef.current.scrollTop
    }
  }, [])

  return (
    <div style={styles.wrapper}>
      <div ref={gutterRef} style={styles.gutter} aria-hidden>
        {Array.from({ length: lineCount }, (_, i) => (
          <div key={i}>{i + 1}</div>
        ))}
      </div>
      <textarea
        ref={textRef}
        style={{ ...styles.editor, ...(readOnly ? styles.readOnly : {}) }}
        value={value}
        rows={rows}
        readOnly={readOnly}
        spellCheck={false}
        onChange={e => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        onScroll={syncScroll}
        onBlur={onBlur}
      />
    </div>
  )
}

const MONO = 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace'
const LINE_HEIGHT = '1.5em'

const styles: Record<string, React.CSSProperties> = {
  wrapper: {
    display: 'flex',
    border: '1px solid #d0d0d0',
    borderRadius: 4,
    background: '#fff',
    overflow: 'hidden',
  },
  gutter: {
    padding: '6px 6px 6px 8px',
    background: '#f7f7f9',
    borderRight: '1px solid #e5e5e5',
    color: '#9ca3af',
    fontFamily: MONO,
    fontSize: 12,
    lineHeight: LINE_HEIGHT,
    textAlign: 'right',
    userSelect: 'none',
    overflow: 'hidden',
  },
  editor: {
    flex: 1,
    border: 'none',
    outline: 'none',
    resize: 'vertical',
    padding: 6,
    fontFamily: MONO,
    fontSize: 12,
    lineHeight: LINE_HEIGHT,
    whiteSpace: 'pre',
    overflowX: 'auto',
  },
  readOnly: {
    background: '#f9fafb',
    color: '#6b7280',
  },
}
